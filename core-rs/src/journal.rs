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

pub const MAGIC: &[u8; 4] = b"HSJ1";
pub const VERSION: u32 = 1;
/// Длина заголовка записи: len(u32) + seq(u64) + crc(u32) + kind(u8).
pub const RECORD_HEADER: usize = 17;

#[derive(Debug, PartialEq, Eq)]
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
        hasher.update(&body);
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

/// Проверка байтов журнала: префикс, коммиты, хвост.
pub fn inspect(bytes: &[u8]) -> Report {
    if bytes.len() < 8 || &bytes[..4] != MAGIC {
        return Report { records: 0, committed: 0, tail_bytes: bytes.len(), torn_tail: false,
                        status: "нет заголовка HSJ1".to_string() };
    }
    let version = u32::from_le_bytes([bytes[4], bytes[5], bytes[6], bytes[7]]);
    if version != VERSION {
        return Report { records: 0, committed: 0, tail_bytes: bytes.len(), torn_tail: false,
                        status: format!("версия {version} не поддерживается") };
    }

    let mut pos = 8usize;
    let mut records = 0usize;
    let mut committed = 0usize;
    let mut expected_seq = 1u64;
    while pos < bytes.len() {
        if bytes.len() - pos < RECORD_HEADER {
            break;
        }
        let length = u32::from_le_bytes([bytes[pos], bytes[pos + 1], bytes[pos + 2], bytes[pos + 3]]) as usize;
        let seq = u64::from_le_bytes(bytes[pos + 4..pos + 12].try_into().unwrap());
        let crc = u32::from_le_bytes([bytes[pos + 12], bytes[pos + 13], bytes[pos + 14], bytes[pos + 15]]);
        let kind = bytes[pos + 16];
        if length > 64 * 1024 * 1024 {
            break;
        }
        let end = pos + RECORD_HEADER + length;
        if end > bytes.len() {
            break; // оборванная запись
        }
        let payload = &bytes[pos + RECORD_HEADER..end];
        let mut hasher = Sha256::new();
        hasher.update(&bytes[pos..pos + 12]);
        hasher.update(payload);
        let digest = hasher.finalize();
        let expected = u32::from_le_bytes([digest[0], digest[1], digest[2], digest[3]]);
        if expected != crc || seq != expected_seq || Kind::from_byte(kind).is_none() {
            break; // порча: дальше не читаем
        }
        if Kind::from_byte(kind) == Some(Kind::Commit) {
            committed += 1;
        }
        records += 1;
        expected_seq += 1;
        pos = end;
    }

    let tail = bytes.len() - pos;
    Report {
        records,
        committed,
        tail_bytes: tail,
        torn_tail: tail > 0,
        status: if tail > 0 { "оборванный хвост в карантине".to_string() } else { "ок".to_string() },
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
        assert!(report.status.contains("HSJ1"));
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
        assert_eq!(&bytes[..4], MAGIC, "файл должен начинаться с HSJ1");
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
}
