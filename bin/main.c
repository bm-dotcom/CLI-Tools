#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <getopt.h>
#include <math.h>

static void print_usage(const char *progname) {
    fprintf(stderr,
        "Usage: %s <command> [options] <file>\n\n"
        "Commands:\n"
        "  hex       Show hex + ASCII dump\n"
        "  entropy   Calculate Shannon entropy (bits/byte)\n"
        "  stats     Show basic file statistics\n\n"
        "Options for 'hex':\n"
        "  -o, --offset <num>   Start at byte offset (default: 0)\n"
        "  -l, --length <num>   Number of bytes to show (default: 256)\n\n"
        "Examples:\n"
        "  %s hex image.png -o 1024 -l 512\n"
        "  %s entropy document.pdf\n",
        progname, progname, progname
    );
}

static void hex_dump(const char *filename, long offset, size_t length) {
    FILE *f = fopen(filename, "rb");
    if (!f) {
        perror("fopen");
        exit(EXIT_FAILURE);
    }

    if (fseek(f, offset, SEEK_SET) != 0) {
        perror("fseek");
        fclose(f);
        exit(EXIT_FAILURE);
    }

    unsigned char *buffer = malloc(length);
    if (!buffer) {
        fprintf(stderr, "malloc failed\n");
        fclose(f);
        exit(EXIT_FAILURE);
    }

    size_t bytes_read = fread(buffer, 1, length, f);
    fclose(f);

    for (size_t i = 0; i < bytes_read; i++) {
        if (i % 16 == 0) {
            printf("\n%08lx  ", (unsigned long)(offset + i));
        }

        printf("%02x ", buffer[i]);

        if (i % 16 == 15 || i == bytes_read - 1) {
            // padding if line is short
            size_t padding = 15 - (i % 16);
            for (size_t p = 0; p < padding; p++) {
                printf("   ");
            }

            printf(" | ");
            size_t line_start = i - (i % 16);
            for (size_t j = line_start; j <= i; j++) {
                unsigned char c = buffer[j];
                putchar((c >= 32 && c <= 126) ? c : '.');
            }
            printf("\n");
        }
    }

    if (bytes_read % 16 != 0) {
        printf("\n");
    }

    free(buffer);
}

static double calculate_entropy(const char *filename) {
    FILE *f = fopen(filename, "rb");
    if (!f) {
        perror("fopen");
        exit(EXIT_FAILURE);
    }

    fseek(f, 0, SEEK_END);
    long file_size = ftell(f);
    if (file_size <= 0) {
        fclose(f);
        return 0.0;
    }

    rewind(f);

    uint64_t freq[256] = {0};
    unsigned char byte;

    while (fread(&byte, 1, 1, f) == 1) {
        freq[byte]++;
    }
    fclose(f);

    double entropy = 0.0;
    for (int i = 0; i < 256; i++) {
        if (freq[i] > 0) {
            double p = (double)freq[i] / file_size;
            entropy -= p * log2(p);
        }
    }

    return entropy;
}

int main(int argc, char *argv[]) {
    if (argc < 2) {
        print_usage(argv[0]);
        return EXIT_FAILURE;
    }

    const char *command = argv[1];

    if (strcmp(command, "hex") == 0) {
        long offset = 0;
        size_t length = 256;

        int c;
        while ((c = getopt(argc - 1, argv + 1, "o:l:")) != -1) {
            switch (c) {
                case 'o':
                    offset = atol(optarg);
                    break;
                case 'l':
                    length = (size_t)atol(optarg);
                    if (length == 0) length = 256;
                    break;
                case '?':
                    print_usage(argv[0]);
                    return EXIT_FAILURE;
            }
        }

        if (optind + 1 >= argc) {
            fprintf(stderr, "Error: missing filename\n");
            print_usage(argv[0]);
            return EXIT_FAILURE;
        }

        const char *filename = argv[optind + 1];
        hex_dump(filename, offset, length);
    }
    else if (strcmp(command, "entropy") == 0) {
        if (argc != 3) {
            fprintf(stderr, "Usage: %s entropy <file>\n", argv[0]);
            return EXIT_FAILURE;
        }
        double e = calculate_entropy(argv[2]);
        printf("Shannon entropy: %.4f bits/byte\n", e);
    }
    else if (strcmp(command, "stats") == 0) {
        if (argc != 3) {
            fprintf(stderr, "Usage: %s stats <file>\n", argv[0]);
            return EXIT_FAILURE;
        }

        FILE *f = fopen(argv[2], "rb");
        if (!f) {
            perror("fopen");
            return EXIT_FAILURE;
        }
        fseek(f, 0, SEEK_END);
        long size = ftell(f);
        fclose(f);

        double entropy = calculate_entropy(argv[2]);

        printf("File:       %s\n", argv[2]);
        printf("Size:       %ld bytes\n", size);
        printf("Entropy:    %.4f bits/byte\n", entropy);
    }
    else {
        fprintf(stderr, "Unknown command: %s\n", command);
        print_usage(argv[0]);
        return EXIT_FAILURE;
    }

    return EXIT_SUCCESS;
}