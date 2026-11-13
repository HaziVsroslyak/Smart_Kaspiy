"""Create the first root interactively; no password is accepted on argv."""
from getpass import getpass
from api.config import Settings
from auth.service import AuthService
from storage import Database


def main() -> None:
    database=Database(Settings.from_environment().database_path)
    database.migrate()
    login=input('Root login: ').strip()
    email=input('Root email: ').strip()
    password=getpass('Root password (12–128 characters): ')
    if password!=getpass('Repeat password: '): raise SystemExit('Passwords differ.')
    user=AuthService(database).create_user(login,email,password,bootstrap=True)
    print(f'Root created: {user.login}')


if __name__=='__main__': main()
