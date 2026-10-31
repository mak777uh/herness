// Минимальная проверка Landlock: доступна ли песочница без прав root и какая ABI.
#include <stdio.h>
#include <unistd.h>
#include <sys/syscall.h>
#include <errno.h>

#ifndef SYS_landlock_create_ruleset
#define SYS_landlock_create_ruleset 444
#endif
#define LANDLOCK_CREATE_RULESET_VERSION (1U << 0)

int main(void) {
    long abi = syscall(SYS_landlock_create_ruleset, NULL, 0, LANDLOCK_CREATE_RULESET_VERSION);
    if (abi < 0) {
        printf("landlock недоступен: errno=%d\n", errno);
        return 1;
    }
    printf("uid=%d landlock ABI=%ld\n", getuid(), abi);
    return 0;
}
