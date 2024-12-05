# IHateDNS
The DNS server for people who hate DNS

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
