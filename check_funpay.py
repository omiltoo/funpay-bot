import inspect
from FunPayAPI import Account

for name in ("get", "get_chats"):
    method = getattr(Account, name)
    print(f"\n===== Account.{name} =====", flush=True)
    print("Файл:", inspect.getfile(method), flush=True)
    print("Строки:", inspect.getsourcelines(method)[1], flush=True)
    print(inspect.getsource(method), flush=True)
