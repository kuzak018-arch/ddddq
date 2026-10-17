import os

# the API's GSI receiver binds a fixed port; tests start their own receiver on a free port instead
os.environ.setdefault("DRAFTER_NO_GSI", "1")
os.environ.setdefault("DRAFTER_NO_PREFETCH", "1")
os.environ.setdefault("DRAFTER_NO_BUILD_LOAD", "1")
