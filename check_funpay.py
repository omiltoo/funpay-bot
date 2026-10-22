import importlib.metadata
import inspect
from FunPayAPI import Account

print("FunPayAPI version:", importlib.metadata.version("FunPayAPI"), flush=True)
print("Account file:", inspect.getfile(Account), flush=True)

for name in ("get", "get_chats"):
    method = getattr(Account, name)
    print(f"\n===== {name} =====", flush=True)
    try:
        lines, start = inspect.getsourcelines(method)
        print("Начальная строка:", start, flush=True)
        print("Количество строк:", len(lines), flush=True)
        for number, line in enumerate(lines, start):
            print(f"{number}: {line}", end="", flush=True)
    except Exception as error:
        print("Не удалось прочитать код:", repr(error), flush=True)
