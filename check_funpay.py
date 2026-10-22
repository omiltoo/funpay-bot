import inspect
import FunPayAPI
from FunPayAPI import Account

print("Путь к библиотеке:", FunPayAPI.__file__)
print("\nМетод Account.get:")
print(inspect.getsource(Account.get))

print("\nМетод Account.get_chats:")
print(inspect.getsource(Account.get_chats))
