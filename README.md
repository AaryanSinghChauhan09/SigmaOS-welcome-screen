    # SigmaOS-welcome-screen

    First-run welcome screen

    Part of the **SigmaOS** sovereign operating-system ecosystem — a multi-repository
    distribution modelled on Linux Mint and Omarchy Linux. See the parent
    [`SigmaOS`](https://github.com/AaryanSinghChauhan09/SigmaOS) repository for the
    full component index.

    ## Upstream inspirations
    - https://github.com/linuxmint/mintwelcome

    ## Design principles applied
    - **Declarative Manifests**
- **Defensive Programming**
- **Fail-Fast**
- **Least Astonishment**
- **KISS**
- **Deterministic Testing**

    ## Usage
    Verbs: `steps, links, tour-plan, finish`

    ```
    $ sigma-welcome steps flow.json
1. [ ] welcome   Welcome to SigmaOS
2. [ ] docs      Read the documentation
$ sigma-welcome steps flow.json --done welcome
1. [x] welcome   Welcome to SigmaOS
$ sigma-welcome links links.json
$ sigma-welcome tour-plan tour.json
[00:30] desktop  Meet the desktop
$ sigma-welcome finish --product SigmaOS --version 1.0 --save ~/.config/welcome.json

    ```

    ## Build & test
    ```
    make build
    make test
    ```

    ## Licence
    GNU General Public License v3.0 (FOSS).
