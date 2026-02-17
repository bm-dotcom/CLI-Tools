CC = clang

CFLAGS = -Wall -Wextra -O2 -std=c11 -lm

all: binprobe

binprobe: main.c
	$(CC) $(CFLAGS) -o binprobe main.c

clean:
	rm -f binprobe

.PHONY: all clean