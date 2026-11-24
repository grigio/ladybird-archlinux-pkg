/* Minimal reproducer for Ladybird issue #15681.
 *
 * Build against the bundled libicudata.so.78 stub from a distribution build:
 *
 *   gcc icu-repro.c -o icu-repro \
 *     -Wl,-rpath,/path/to/stub-dir -L/path/to/stub-dir -l:libicudata.so.78.3
 *   ./icu-repro    // SIGSEGV in ld-linux on glibc 2.44
 *
 * Linking against a full libicudata.so.78.3 exits 0.
 */

extern char icudt78_dat[];

int main(void)
{
    return icudt78_dat[0] == 0;
}
