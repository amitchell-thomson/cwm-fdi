#include <stdio.h>
#include <string.h>
#include <stdlib.h>

/*
 * CTF notes:
 * - Program flow is unchanged.
 * - The vulnerability remains in process_command() via gets().
 * - The flag is printed only if control flow is redirected to win().
 */

static const char FLAG[] = "CTF{S3CURITY_CWM_WIN_2_EZ}";

/* Ensure the function is present and easy to locate in the binary */
__attribute__((noinline, used))
void win(void) {
    puts("\n=====================================");
    puts("              ACCESS GRANTED         ");
    puts("=====================================");
    printf("FLAG: %s\n", FLAG);
    fflush(stdout);
    exit(0);
}

void print_banner() {
    printf("=====================================\n");
    printf("    SECURE AUTHENTICATION SYSTEM    \n");
    printf("=====================================\n");
    printf("Welcome to the secure login system!\n");
}

int validate_username(char* username) {
    // This function is safe - no vulnerability here
    char valid_user[] = "admin";
    return strcmp(username, valid_user) == 0;
}

void get_user_info() {
    char name[32];
    char department[64];

    printf("Enter your name: "); fflush(stdout);
    fgets(name, sizeof(name), stdin);
    name[strcspn(name, "\n")] = '\0';  // Remove newline

    printf("Enter your department: "); fflush(stdout);
    fgets(department, sizeof(department), stdin);
    department[strcspn(department, "\n")] = '\0';

    printf("Thank you %s from %s!\n", name, department); fflush(stdout);

    // This function seems safe too...
}

void process_command() {
    char response[256]; // What would happen if this was declared second? Why?
    char command[128];

    printf("Enter system command to process: "); fflush(stdout);
    fgets(command, sizeof(command), stdin);
    command[strcspn(command, "\n")] = '\0';

    printf("Processing command: %s\n", command); fflush(stdout);

    // Simulate some processing
    printf("Enter response data: "); fflush(stdout);
    gets(response);  // VULNERABILITY! Using gets() instead of fgets()

    printf("Response processed: %s\n", response); fflush(stdout);
}

void authenticate_user() {
    char username[16];
    char password[32];
    int attempts = 0;

    while (attempts < 3) {

        // validate username //
        printf("\nUsername: "); fflush(stdout);
        fgets(username, sizeof(username), stdin);
        username[strcspn(username, "\n")] = '\0';

        if (!validate_username(username)) {
            printf("Invalid username!\n"); fflush(stdout);
            attempts++;
            continue;
        }

        // validate password //
        printf("Password: "); fflush(stdout);
        fgets(password, sizeof(password), stdin);
        password[strcspn(password, "\n")] = '\0';

        // Simple password check (in real systems this would be hashed)
        if (strcmp(password, "secure123") == 0) {
            printf("Authentication successful!\n"); fflush(stdout);
            return;
        } else {
            printf("Invalid password!\n"); fflush(stdout);
            attempts++;
        }
    }

    printf("Too many failed attempts. Exiting.\n"); fflush(stdout);
    exit(1);
}

int main() {
    print_banner();

    // Stage 1: Authentication (safe)
    authenticate_user();

    // Stage 2: User info collection (safe)
    get_user_info();

    // Stage 3: Command processing (VULNERABLE!)
    process_command();

    printf("All operations completed successfully.\n"); fflush(stdout);
    return 0;
}
