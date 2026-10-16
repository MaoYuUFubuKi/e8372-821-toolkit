import sys
from .cli import main

try:
    sys.exit(main())
except Exception as error:
    print('停止：'+str(error),file=sys.stderr)
    sys.exit(1)
