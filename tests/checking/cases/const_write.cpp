// The same mistake, without casting the const away: C++ refuses it outright.
static const char msg[] = "hi";
int main() {
    msg[0] = 'A';                               // MISTAKE
    return msg[1];
}
