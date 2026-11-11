//! Журнал: append-only с явной границей коммита, CRC на запись и карантином оборванного хвоста.
//!
//! Решения взяты из P20 (research/P20-RESULTS-2026-10-31.md):
//! - заголовок файла: magic + версия;
//! - запись: длина, номер, CRC, полезная нагрузка;
//! - отдельная запись-маркер коммита: «запись есть» ≠ «запись подтверждена»;
//! - восстановление читает непрерывный валидный префикс и останавливается на первой невалидной
//!   записи; хвост не «починяется», а помещается в карантин;
//! - подтверждение вызывающему — только после fsync (политика задаётся снаружи).

use std::fs::{self, File, OpenOptions};
use std::io::{Read, Seek, SeekFrom, Write};
use std::path::{Path, PathBuf};
use std::time::{SystemTime, UNIX_EPOCH};

use sha2::{Digest, Sha256};

pub const MAGIC: &[u8; 4] = b"HSJ2";
pub const VERSION: u32 = 2;
/// Длина заголовка записи: len(u32) + seq(u64) + crc(u32) + kind(u8).
/// HSJ2 (ADR-0056): crc покрывает len+seq+kind+payload; раскладка записи не изменилась.
pub const RECORD_HEADER: usize = 17;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Kind {
    Data,
    Commit,
}

impl Kind {
    fn byte(&self) -> u8 {
        match self {
            Kind::Data => 1,
            Kind::Commit => 2,
        }
    }

    fn from_byte(value: u8) -> Option<Kind> {
        match value {
            1 => Some(Kind::Data),
            2 => Some(Kind::Commit),
            _ => None,
        }
    }
}

/// Что нашли при проверке журнала.
#[derive(Debug, PartialEq, Eq)]
pub struct Report {
    pub records: usize,
    pub committed: usize,
    pub tail_bytes: usize,
    pub torn_tail: bool,
    pub status: String,
}

fn header() -> Vec<u8> {
    let mut bytes = Vec::with_capacity(8);
    bytes.extend_from_slice(MAGIC);
    bytes.extend_from_slice(&VERSION.to_le_bytes());
    bytes
}

pub struct Journal {
    path: PathBuf,
    file: File,
    seq: u64,
    pending: usize,
    dirty: bool,
}

impl Journal {
    /// Открыть или создать журнал. При первом открытии файл получает заголовок.
    pub fn open(path: impl AsRef<Path>) -> std::io::Result<Journal> {
        let path = path.as_ref().to_path_buf();
        let mut file = OpenOptions::new().read(true).write(true).create(true).open(&path)?;
        let length = file.metadata()?.len();
        if length == 0 {
            file.write_all(&header())?;
            file.sync_all()?;
        } else {
            // HSJ2 (ADR-0056): оборванный хвост не перезаписываем. Карантин + обрезка до
            // валидного префикса (зеркально run_task_resume): валидные записи не теряются,
            // хвост сохраняется в карантинном файле, продолжение становится читаемым.
            let report = inspect(&fs::read(&path)?);
            if report.torn_tail {
                quarantine(&path)?;
                let valid = file.metadata()?.len() - report.tail_bytes as u64;
                file.set_len(valid)?;
                file.sync_all()?;
            }
            // Существующий журнал: писать можно только в конец, иначе затрём историю.
            file.seek(SeekFrom::End(0))?;
        }
        let mut journal = Journal { path, file, seq: 0, pending: 0, dirty: false };
        journal.seq = journal.report()?.records as u64;
        Ok(journal)
    }

    pub fn append(&mut self, payload: &[u8], kind: Kind) -> std::io::Result<u64> {
        self.seq += 1;
        let mut body = Vec::with_capacity(RECORD_HEADER + payload.len());
        body.extend_from_slice(&(payload.len() as u32).to_le_bytes());
        body.extend_from_slice(&self.seq.to_le_bytes());
        let mut hasher = Sha256::new();
        hasher.update(&body); // len + seq (12 байт)
        hasher.update([kind.byte()]); // HSJ2: kind входит в CRC (ADR-0056)
        hasher.update(payload);
        let digest = hasher.finalize();
        let crc = u32::from_le_bytes([digest[0], digest[1], digest[2], digest[3]]);
        body.extend_from_slice(&crc.to_le_bytes());
        body.push(kind.byte());
        body.extend_from_slice(payload);
        self.file.write_all(&body)?;
        self.pending += 1;
        self.dirty = true;
        Ok(self.seq)
    }

    /// Политика долговечности: сбросить, если накопилось `max_pending` записей.
    pub fn maybe_sync(&mut self, max_pending: usize) -> std::io::Result<bool> {
        if self.dirty && self.pending >= max_pending {
            self.file.sync_all()?;
            self.pending = 0;
            self.dirty = false;
            return Ok(true);
        }
        Ok(false)
    }

    pub fn sync(&mut self) -> std::io::Result<()> {
        if self.dirty {
            self.file.sync_all()?;
            self.pending = 0;
            self.dirty = false;
        }
        Ok(())
    }

    /// Проверка: читает префикс и сообщает, где кончился валидный кусок.
    pub fn report(&self) -> std::io::Result<Report> {
        let mut file = File::open(&self.path)?;
        let mut bytes = Vec::new();
        file.read_to_end(&mut bytes)?;
        Ok(inspect(&bytes))
    }
}

/// Разобранная запись журнала: что именно было записано, а не только сколько.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Entry {
    pub kind: Kind,
    pub payload: Vec<u8>,
}

/// Результат разбора: валидный префикс записей и длина непрочитанного хвоста.
#[derive(Debug, Clone, Default)]
pub struct Walk {
    pub entries: Vec<Entry>,
    pub tail_bytes: usize,
}

/// Разобрать журнал до первой невалидной записи.
///
/// Ошибка возвращается только для заголовка: без magic или с чужой версией читать нечего.
/// Оборванная или испорченная запись — это не ошибка разбора, а `tail_bytes`: так же, как в
/// восстановлении, мы не «чиним» и не гадаем.
pub fn walk(bytes: &[u8]) -> Result<Walk, String> {
    if bytes.len() < 8 || &bytes[..4] != MAGIC {
        return Err("нет заголовка HSJ2".to_string());
    }
    let version = u32::from_le_bytes([bytes[4], bytes[5], bytes[6], bytes[7]]);
    if version != VERSION {
        return Err(format!("версия {version} не поддерживается"));
    }

    let mut pos = 8usize;
    let mut entries: Vec<Entry> = Vec::new();
    let mut expected_seq = 1u64;
    while pos < bytes.len() {
        if bytes.len() - pos < RECORD_HEADER {
            break;
        }
        let length =
            u32::from_le_bytes([bytes[pos], bytes[pos + 1], bytes[pos + 2], bytes[pos + 3]]) as usize;
        let seq = u64::from_le_bytes(bytes[pos + 4..pos + 12].try_into().unwrap());
        let crc = u32::from_le_bytes([bytes[pos + 12], bytes[pos + 13], bytes[pos + 14], bytes[pos + 15]]);
        let kind_byte = bytes[pos + 16];
        if length > 64 * 1024 * 1024 {
            break;
        }
        let end = pos + RECORD_HEADER + length;
        if end > bytes.len() {
            break; // оборванная запись
        }
        let payload = &bytes[pos + RECORD_HEADER..end];
        let mut hasher = Sha256::new();
        hasher.update(&bytes[pos..pos + 12]); // len + seq
        hasher.update([kind_byte]); // HSJ2: kind входит в CRC (ADR-0056)
        hasher.update(payload);
        let digest = hasher.finalize();
        let expected = u32::from_le_bytes([digest[0], digest[1], digest[2], digest[3]]);
        let Some(kind) = Kind::from_byte(kind_byte) else { break };
        if expected != crc || seq != expected_seq {
            break; // порча: дальше не читаем
        }
        entries.push(Entry { kind, payload: payload.to_vec() });
        expected_seq += 1;
        pos = end;
    }

    Ok(Walk { entries, tail_bytes: bytes.len() - pos })
}

/// Проверка байтов журнала: префикс, коммиты, хвост.
pub fn inspect(bytes: &[u8]) -> Report {
    match walk(bytes) {
        Err(status) => Report {
            records: 0,
            committed: 0,
            tail_bytes: bytes.len(),
            torn_tail: false,
            status,
        },
        Ok(walked) => {
            let records = walked.entries.len();
            let committed = walked
                .entries
                .iter()
                .filter(|entry| entry.kind == Kind::Commit)
                .count();
            let tail = walked.tail_bytes;
            Report {
                records,
                committed,
                tail_bytes: tail,
                torn_tail: tail > 0,
                status: if tail > 0 {
                    "оборванный хвост в карантине".to_string()
                } else {
                    "ок".to_string()
                },
            }
        }
    }
}

/// Вынести оборванный хвост в отдельный файл, не трогая журнал (карантин, не автопочинка).
pub fn quarantine(path: impl AsRef<Path>) -> std::io::Result<Option<PathBuf>> {
    let path = path.as_ref();
    let bytes = fs::read(path)?;
    let report = inspect(&bytes);
    if !report.torn_tail {
        return Ok(None);
    }
    let stamp = SystemTime::now().duration_since(UNIX_EPOCH).map(|d| d.as_secs()).unwrap_or(0);
    let target = path.with_extension(format!("tail-{stamp}.bin"));
    let offset = bytes.len() - report.tail_bytes;
    fs::write(&target, &bytes[offset..])?;
    Ok(Some(target))
}

#[cfg(test)]
mod tests {
    use super::*;

    fn tmp(name: &str) -> PathBuf {
        std::env::temp_dir().join(name)
    }

    #[test]
    fn append_and_recover() {
        let path = tmp("hsj_ok.bin");
        let _ = fs::remove_file(&path);
        let mut journal = Journal::open(&path).unwrap();
        journal.append(b"{\"seq\":1}", Kind::Data).unwrap();
        journal.append(b"commit", Kind::Commit).unwrap();
        journal.sync().unwrap();
        let report = journal.report().unwrap();
        assert_eq!(report.records, 2);
        assert_eq!(report.committed, 1);
        assert!(!report.torn_tail);
        assert_eq!(report.status, "ок");
    }

    #[test]
    fn torn_tail_is_detected_not_repaired() {
        let path = tmp("hsj_torn.bin");
        let _ = fs::remove_file(&path);
        {
            let mut journal = Journal::open(&path).unwrap();
            journal.append(b"first", Kind::Data).unwrap();
            journal.append(b"second", Kind::Data).unwrap();
            journal.sync().unwrap();
        }
        // обрываем файл внутри второй записи
        let bytes = fs::read(&path).unwrap();
        let cut = bytes.len() - 3;
        fs::write(&path, &bytes[..cut]).unwrap();

        let report = inspect(&fs::read(&path).unwrap());
        assert!(report.torn_tail, "обрыв должен быть виден");
        assert_eq!(report.records, 1, "валидный префикс — одна запись");
        assert!(report.tail_bytes > 0);

        let quarantined = quarantine(&path).unwrap();
        assert!(quarantined.is_some(), "хвост должен уйти в карантин");
        // журнал не изменился: починки нет
        assert_eq!(fs::read(&path).unwrap().len(), cut);
    }

    #[test]
    fn corrupted_record_stops_reading() {
        let path = tmp("hsj_corrupt.bin");
        let _ = fs::remove_file(&path);
        {
            let mut journal = Journal::open(&path).unwrap();
            journal.append(b"alpha", Kind::Data).unwrap();
            journal.append(b"beta", Kind::Data).unwrap();
            journal.sync().unwrap();
        }
        let mut bytes = fs::read(&path).unwrap();
        let last = bytes.len() - 1;
        bytes[last] ^= 0xFF; // портим последний байт второй записи
        fs::write(&path, &bytes).unwrap();
        let report = inspect(&fs::read(&path).unwrap());
        assert_eq!(report.records, 1, "после порчи чтение прекращается");
        assert!(report.torn_tail);
    }

    #[test]
    fn bad_magic_is_reported() {
        let report = inspect(b"XXXX\x01\x00\x00\x00");
        assert_eq!(report.records, 0);
        assert!(report.status.contains("HSJ2"));
    }

    #[test]
    fn commit_boundary_counts() {
        let path = tmp("hsj_commit.bin");
        let _ = fs::remove_file(&path);
        let mut journal = Journal::open(&path).unwrap();
        for index in 0..3 {
            journal.append(format!("record-{index}").as_bytes(), Kind::Data).unwrap();
        }
        assert_eq!(journal.report().unwrap().committed, 0, "без коммита границы нет");
        journal.append(b"commit", Kind::Commit).unwrap();
        journal.sync().unwrap();
        let report = journal.report().unwrap();
        assert_eq!(report.records, 4);
        assert_eq!(report.committed, 1);
    }

    #[test]
    fn file_starts_with_magic() {
        let path = tmp("hsj_magic.bin");
        let _ = fs::remove_file(&path);
        let mut journal = Journal::open(&path).unwrap();
        journal.append(b"payload", Kind::Data).unwrap();
        journal.sync().unwrap();
        let bytes = fs::read(&path).unwrap();
        assert_eq!(&bytes[..4], MAGIC, "файл должен начинаться с HSJ2");
        assert_eq!(&bytes[4..8], &VERSION.to_le_bytes(), "после magic идёт версия");
    }

    #[test]
    fn append_to_existing_keeps_prefix() {
        let path = tmp("hsj_reopen.bin");
        let _ = fs::remove_file(&path);
        {
            let mut journal = Journal::open(&path).unwrap();
            journal.append(b"first", Kind::Data).unwrap();
            journal.append(b"commit", Kind::Commit).unwrap();
            journal.sync().unwrap();
        }
        // повторное открытие: история не должна пострадать
        {
            let mut journal = Journal::open(&path).unwrap();
            journal.append(b"second", Kind::Data).unwrap();
            journal.sync().unwrap();
        }
        let bytes = fs::read(&path).unwrap();
        assert_eq!(&bytes[..4], MAGIC, "заголовок должен остаться первым");
        let report = inspect(&bytes);
        assert_eq!(report.records, 3, "три записи: first, commit, second");
        assert_eq!(report.committed, 1);
        assert!(!report.torn_tail);
    }

    #[test]
    fn kind_flip_is_detected() {
        // Негативный контроль HSJ2-KIND-R1: переворот kind Data->Commit БЕЗ пересчёта CRC
        // обязан отвергаться. На HSJ1 (kind вне CRC) проходит — это дефект; на HSJ2 — отказ.
        let path = tmp("hsj_kindflip.bin");
        let _ = fs::remove_file(&path);
        {
            let mut journal = Journal::open(&path).unwrap();
            journal.append(b"run/end answer", Kind::Data).unwrap();
            journal.append(b"commit", Kind::Commit).unwrap();
            journal.sync().unwrap();
        }
        let original = fs::read(&path).unwrap();
        // Положительный контроль: неперевёрнутый журнал разбирается полностью.
        let clean = inspect(&original);
        assert_eq!(clean.records, 2, "исходный журнал: две записи");
        assert!(!clean.torn_tail, "исходный журнал без хвоста");

        // kind первой записи: header(8) + len(4) + seq(8) + crc(4) = offset 24.
        let mut bytes = original.clone();
        let kind_pos = 8 + 16;
        assert_eq!(bytes[kind_pos], 1, "первая запись должна быть Data");
        bytes[kind_pos] = 2; // Data -> Commit, CRC не трогаем
        let report = inspect(&bytes);
        assert!(report.torn_tail, "переворот kind обязан быть отвергнут (хвост в карантине)");
        assert_eq!(report.records, 0, "перевёрнутая запись не должна приниматься");
    }

    #[test]
    fn open_quarantines_torn_tail_without_losing_prefix() {
        // Смежный дефект HSJ2-KIND-R1: open() на оборванном хвосте обязан карантинить хвост
        // и обрезать до валидного префикса (зеркально run_task_resume), не теряя записи.
        let path = tmp("hsj_open_torn.bin");
        let _ = fs::remove_file(&path);
        {
            let mut journal = Journal::open(&path).unwrap();
            journal.append(b"first", Kind::Data).unwrap();
            journal.append(b"second", Kind::Data).unwrap();
            journal.sync().unwrap();
        }
        let bytes = fs::read(&path).unwrap();
        let cut = bytes.len() - 3; // обрыв внутри второй записи
        fs::write(&path, &bytes[..cut]).unwrap();
        assert!(inspect(&fs::read(&path).unwrap()).torn_tail, "хвост должен быть оборван");

        {
            let mut journal = Journal::open(&path).unwrap();
            journal.append(b"third", Kind::Data).unwrap();
            journal.sync().unwrap();
        }
        let report = inspect(&fs::read(&path).unwrap());
        assert!(!report.torn_tail, "после open хвост обрезан, продолжение читаемо");
        assert_eq!(report.records, 2, "first + third: валидный префикс не потерян");

        let quarantined: Vec<_> = fs::read_dir(std::env::temp_dir())
            .unwrap()
            .filter_map(|entry| entry.ok())
            .filter(|entry| entry.file_name().to_string_lossy().starts_with("hsj_open_torn.tail-"))
            .collect();
        assert!(!quarantined.is_empty(), "оборванный хвост должен уйти в карантин");
    }

    #[test]
    fn hsj2_frame_cross_vector_matches_python() {
        // Кросс-сверка HSJ2-кадра (ADR-0056): замороженные байты, посчитанные эталонной
        // Python-формулой (CRC = sha256(len++seq++kind++payload)[0..4]), обязаны разбираться
        // Rust walk() и совпадать по kind и CRC. Переворот kind без пересчёта CRC — отказ.
        // Вектор лежит в tests/vectors (корень репозитория), как journal.json/seal.json.
        let path = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
            .parent()
            .expect("корень репозитория")
            .join("tests")
            .join("vectors")
            .join("journal_frame.json");
        let raw = fs::read_to_string(&path).expect("вектор HSJ2-кадра");
        let vec: serde_json::Value = serde_json::from_str(&raw).expect("валидный JSON");
        let bytes = hex::decode(vec["hex"].as_str().expect("hex")).expect("hex байты");

        // 1. Производственный разбор принимает эталонные байты без хвоста.
        let walked = walk(&bytes).expect("walk не должен ошибиться на валидном HSJ2");
        let records = vec["records"].as_array().expect("records");
        assert_eq!(walked.entries.len(), records.len(), "число записей");
        assert_eq!(walked.tail_bytes, 0, "валидный кадр без хвоста");
        for (entry, m) in walked.entries.iter().zip(records.iter()) {
            let kind_byte = match entry.kind { Kind::Data => 1u8, Kind::Commit => 2u8 };
            assert_eq!(kind_byte, m["kind"].as_u64().expect("kind") as u8, "kind расходится");
            assert_eq!(entry.payload, m["payload"].as_str().expect("payload").as_bytes(),
                       "payload расходится");
        }

        // 2. CRC каждого кадра, пересчитанный Rust sha2, совпадает с замороженным литералом.
        for m in records {
            let seq = m["seq"].as_u64().expect("seq");
            let kind = m["kind"].as_u64().expect("kind") as u8;
            let payload = m["payload"].as_str().expect("payload").as_bytes();
            let mut head = Vec::new();
            head.extend_from_slice(&(payload.len() as u32).to_le_bytes());
            head.extend_from_slice(&seq.to_le_bytes());
            let mut hasher = Sha256::new();
            hasher.update(&head);
            hasher.update([kind]);
            hasher.update(payload);
            let digest = hasher.finalize();
            let crc = hex::encode(&digest[..4]);
            assert_eq!(crc, m["crc"].as_str().expect("crc"), "CRC кадра расходится с Python");
        }

        // 3. Замороженный негативный контроль: переворот kind без пересчёта CRC — отказ.
        let kf = &vec["kind_flip"];
        let offset = kf["offset"].as_u64().expect("offset") as usize;
        let mut bad = bytes.clone();
        assert_eq!(bad[offset], kf["from"].as_u64().expect("from") as u8);
        bad[offset] = kf["to"].as_u64().expect("to") as u8;
        let rejected = walk(&bad).expect("walk не ошибается на оборванном кадре");
        assert_eq!(rejected.entries.len(), 0, "перевёрнутый kind не должен приниматься");
        assert!(rejected.tail_bytes > 0, "переворот kind обязан уйти в хвост");
    }
}
