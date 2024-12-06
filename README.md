# IHateDNS

A DNS server with a RESTful HTTP API for updating records, intended for internal testing.

### Invocation

```
$ python3 ihatedns.py --help
usage: ihatedns.py [-h] [--db DB] [--host HOST] [--dns-port DNS_PORT]
                   [--http-port HTTP_PORT]

The DNS server for people who hate DNS

options:
  -h, --help            show this help message and exit
  --db DB               sqlite3 db path for persisting records (defaults to
                        :memory: i.e. no persistence)
  --host HOST           listen host (default '127.0.0.1')
  --dns-port DNS_PORT   default 5337 (UDP)
  --http-port HTTP_PORT
                        default 8053
```

### Usage Examples

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

### Protip

Put this in your `/etc/systemd/resolved.conf`:
```
[Resolve]
DNS=127.0.0.1:5337
```
And then reload the config
```sh
sudo systemctl restart systemd-resolved.service
```

(Note, this config will race queries against whatever your default resolver is. I think)

### TODO

- Optionally, forward requests to another resolver
- Deleting individual records
- Make it a proper python package and switch to pyproject.toml
- More options - log levels, separate DNS/HTTP listen host?
- TCP DNS
- Do something sensible if the UDP response would be too long
