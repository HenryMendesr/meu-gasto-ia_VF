"""Password changes and one-use recovery codes, with no email dependency."""
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from pathlib import Path

try:
    from src import auth, runtime_storage as storage
except ImportError:
    import auth
    import runtime_storage as storage


def validate_password(password):
    if not isinstance(password,str) or not 10<=len(password)<=200:
        raise ValueError('Use uma senha de 10 a 200 caracteres')


def code_hash(code):
    return hashlib.sha256(str(code).replace('-','').replace(' ','').lower().encode()).hexdigest()


def codes():
    values=[secrets.token_hex(16) for _ in range(6)]
    return ['-'.join(value[index:index+8] for index in range(0,32,8)) for value in values]


def local_supported():
    return not os.environ.get('APP_PASSWORD') and auth.AUTH_FILE.exists()


def save_local(data):
    auth.AUTH_FILE.parent.mkdir(parents=True,exist_ok=True)
    handle,name=tempfile.mkstemp(prefix='access-',suffix='.json',dir=auth.AUTH_FILE.parent)
    try:
        with os.fdopen(handle,'w',encoding='utf-8') as stream:json.dump(data,stream)
        os.chmod(name,0o600);Path(name).replace(auth.AUTH_FILE)
    finally:Path(name).unlink(missing_ok=True)


def verify(password,user_id=None):
    if os.environ.get('DATABASE_URL'):
        return storage.verify_account_password(user_id,password)
    return auth.verify_password(password)


def change_password(old,new,user_id=None):
    validate_password(new)
    if os.environ.get('DATABASE_URL'):
        return storage.change_account_password(user_id,old,new)
    if not local_supported():raise ValueError('A senha deste acesso é definida na configuração do servidor')
    if not verify(old):raise ValueError('Senha atual incorreta')
    data=auth._read();salt=secrets.token_bytes(16)
    data.update(salt=auth._encode(salt),password_hash=auth._encode(hashlib.pbkdf2_hmac('sha256',new.encode(),salt,auth.PBKDF2_ITERATIONS)),session_version=data.get('session_version',0)+1)
    save_local(data);return data['session_version']


def generate_codes(password,user_id=None):
    values=codes()
    if os.environ.get('DATABASE_URL'):
        storage.set_recovery_codes(user_id,password,[code_hash(code) for code in values]);return values
    if not local_supported():raise ValueError('Recuperação indisponível para senha definida pelo servidor')
    if not verify(password):raise ValueError('Senha atual incorreta')
    data=auth._read();data['recovery_hashes']=[code_hash(code) for code in values];save_local(data);return values


def recover(email,code,password):
    validate_password(password)
    if os.environ.get('DATABASE_URL'):
        return storage.recover_account(email,code_hash(code),password)
    if not local_supported():raise ValueError('Não foi possível recuperar o acesso com estes dados')
    data=auth._read();expected=code_hash(code);hashes=data.get('recovery_hashes',[])
    found=next((value for value in hashes if hmac.compare_digest(value,expected)),None)
    if not found:raise ValueError('Não foi possível recuperar o acesso com estes dados')
    salt=secrets.token_bytes(16);hashes.remove(found)
    data.update(salt=auth._encode(salt),password_hash=auth._encode(hashlib.pbkdf2_hmac('sha256',password.encode(),salt,auth.PBKDF2_ITERATIONS)),recovery_hashes=hashes,session_version=data.get('session_version',0)+1)
    save_local(data);return True


def status(user_id=None):
    if os.environ.get('DATABASE_URL'):
        return storage.account_security_status(user_id)
    data=auth._read() if local_supported() else {}
    return {'password_management':local_supported(),'recovery_codes_remaining':len(data.get('recovery_hashes',[]))}
