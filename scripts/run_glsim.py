"""Start GLSim with the gltest Windows temp-file compatibility fix."""

import atexit

from testing.windows_loader import cleanup, install


if __name__ == "__main__":
    install()
    atexit.register(cleanup)
    from glsim.__main__ import main

    main()
