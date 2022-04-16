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
