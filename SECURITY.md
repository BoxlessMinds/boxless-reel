# Security Policy

## Supported versions

Boxless Reel is maintained by one person in their spare time. Security fixes go into the latest release only.

| Version | Supported |
|---|---|
| Latest release | Yes |
| Anything older | No, please upgrade |

## Reporting a vulnerability

**Please don't report security problems in public issues, discussions or pull requests.**

Report them privately through GitHub's private vulnerability reporting instead:

1. Go to the repository's **Security** tab.
2. Click **Report a vulnerability**.
3. Describe the problem, how to reproduce it, and what an attacker could do with it.

If you can't use GitHub, email [info@boxlessminds.com](mailto:info@boxlessminds.com) with "Security" in the subject line.

## What to expect

- Your report will be acknowledged within 7 days.
- I'll confirm whether it's a real vulnerability and keep you updated while I work on a fix.
- Once a fix is released, I'll publish a security advisory. I'll credit you in it unless you'd rather stay anonymous.

Please give me a reasonable amount of time to release a fix before you disclose the problem publicly.

## Scope

**In scope:** the code in this repository: the API, the web UI, and the Docker setup as shipped.

**Out of scope:**

- Problems in third-party dependencies. Please report those to the dependency's maintainers. If one affects Boxless Reel in a specific way, a heads-up here is still welcome.
- A self-hosted instance that's insecure because of how it was set up, for example weak secrets, an app exposed to the internet without TLS, or open registration turned on deliberately.
- YouTube or Google blocking or rate-limiting requests. That's a service limitation, not a vulnerability.

## Handling secrets

Never include real API keys, passwords or tokens in a report, an issue or a pull request. If you accidentally expose one of your own, revoke it with the provider right away.
