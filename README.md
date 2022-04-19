# ad_kihon
"Kihon" in Karate is the set of basic techniques. <br>
This attack/defense framework is called ```ad_kihon``` because it is aimed for team training in a local environment. <br>
Also, it was developed with these requirements in mind:

- Easy & documented architecture ([KISS principle](https://en.wikipedia.org/wiki/KISS_principle)), which enables ```mantainability``` and ```testability```;
- Easy deployment (no local build, just copy the docker-compose which uses the pre-built images, and create a volume folder with the configuration file and the checkers: clone the repository only if you want a clean project structure to write checkers);
- Security: there is an high test coverage of the backend, to handle all the edge cases, input validation for data coming in, some DoS protection and protections against concurrency issues.

## Status
Development

## Instructions
TODO

```
$ curl -X POST http://127.0.0.1:8080/api/flagSubmit -H 'Content-Type: application/json' -d '{"token": "c2e192800a294acbb2ac7dd188502edb", "flags": ["flag{61b858b581964ed2b4935987be306b}"]}'
{"num_invalid": 0, "num_accepted": 1, "num_already_submitted": 0, "num_self_flags": 0, "num_discarded": 0, "num_old": 0}
```
