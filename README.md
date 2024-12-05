# IHateDNS

```
$ python3 ihatedns.py --help
usage: ihatedns.py [-h] [--db DB] [--host HOST] [--dns-port DNS_PORT][--http-port HTTP_PORT]

The DNS server for those who hate DNS

options:
  -h, --help            show this help message and exit
  --db DB               sqlite3 database path (defaults to :memory:)
  --host HOST           listen host (default '127.0.0.1')
  --dns-port DNS_PORT   default 5337 (UDP)
  --http-port HTTP_PORT
                        default 8053
```

```sh
# no config files, just REST
$ curl -X PUT http://localhost:8053/example.com/a/1.2.3.4,8.8.8.8
$ dig -p 5337 @127.0.0.1 +noall +answer example.com
example.com.            60      IN      A       1.2.3.4
example.com.            60      IN      A       8.8.8.8

# ~all record types supported
$ curl -X PUT http://localhost:8053/_atproto.bob.test/TXT/did=did:web:bob.test
$ dig -p 5337 @127.0.0.1 +noall +answer TXT _atproto.bob.test
_atproto.bob.test.      60      IN      TXT     "did=did:web:bob.test"

# inspect your records over HTTP, too
$ curl http://localhost:8053/_atproto.bob.test/TXT/
_atproto.bob.test. 60 IN TXT "did=did:web:bob.test"

$ curl http://localhost:8053/
example.com. 60 IN A 1.2.3.4
example.com. 60 IN A 8.8.8.8
_atproto.bob.test. 60 IN TXT "did=did:web:bob.test"
```
