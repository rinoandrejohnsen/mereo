#!/usr/bin/env python3
"""Generate Common Log Format traffic. `gen.py N [seed]` -> N lines on stdout."""
import random, sys

PATHS = ["/", "/index.html", "/api/v1/users", "/api/v1/orders", "/static/app.js",
         "/static/app.css", "/img/logo.png", "/favicon.ico", "/health",
         "/api/v1/search", "/docs/", "/docs/guide", "/login", "/logout"]
STATUS = [200] * 70 + [304] * 10 + [404] * 8 + [301] * 5 + [500] * 4 + [403] * 3
METHOD = ["GET"] * 85 + ["POST"] * 10 + ["HEAD"] * 5

n = int(sys.argv[1])
r = random.Random(int(sys.argv[2]) if len(sys.argv) > 2 else 1)
w = sys.stdout.write
for i in range(n):
    host = f"{r.randint(1,254)}.{r.randint(0,255)}.{r.randint(0,255)}.{r.randint(1,254)}"
    path = r.choice(PATHS)
    if r.random() < 0.15:
        path += f"?id={r.randint(1, 9999)}"
    st = r.choice(STATUS)
    nb = "-" if st in (304, 204) else str(r.randint(120, 78000))
    w(f'{host} - - [10/Oct/2000:13:55:{i % 60:02d} -0700] '
      f'"{r.choice(METHOD)} {path} HTTP/1.1" {st} {nb}\n')
