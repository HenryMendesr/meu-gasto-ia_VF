"""Account controls shared by the local server and the hosted API."""
import os

try:
    from src import investments, runtime_storage as storage, account_security, portability, auth
except ImportError:
    import investments
    import runtime_storage as storage
    import account_security
    import portability
    import auth

VERSION='2026.10.29.1'


def status(user_id=None):
    hosted=bool(os.environ.get('DATABASE_URL'))
    profile=storage.get_user(user_id) if hosted else {'id':1,'name':'Conta local','email':''}
    data=investments.load_store(user_id)
    return {'profile':profile,'security':account_security.status(user_id),
            'can_delete':hosted or account_security.local_supported(),
            'hosted':hosted,'preferences':data.get('preferences',{}),
            'previous_backup':storage.backup_metadata(user_id),
            'audit':data.get('audit_log',[])[-50:],'version':VERSION}


def check_password(password,user_id):
    if not isinstance(password,str) or not account_security.verify(password,user_id):
        raise ValueError('Senha atual incorreta')


def preview_restore(payload,user_id=None):
    data=portability.validate(payload)
    return {'counts':portability.counts(data),'current':portability.counts(storage.export_financial_data(user_id)['data'])}


def restore(payload,user_id=None):
    if not isinstance(payload,dict) or payload.get('confirmation')!='RESTAURAR':raise ValueError('Digite RESTAURAR para substituir os dados desta conta')
    check_password(payload.get('password'),user_id)
    result=storage.restore_financial_data(payload.get('backup'),user_id)
    return {'counts':result}


def delete(payload,user_id=None):
    if not isinstance(payload,dict) or payload.get('confirmation')!='EXCLUIR':raise ValueError('Digite EXCLUIR para confirmar')
    hosted=bool(os.environ.get('DATABASE_URL'))
    if not hosted and not account_security.local_supported():raise ValueError('A exclusão deste acesso depende da configuração do servidor')
    check_password(payload.get('password'),user_id)
    storage.delete_financial_account(user_id)
    if not hosted:auth.AUTH_FILE.unlink(missing_ok=True)
    return {'redirect':'/login' if hosted else '/setup'}


def diagnostic(user_id=None):
    hosted=bool(os.environ.get('DATABASE_URL'))
    connected=storage.database_status()['connected'] if hosted else bool(storage.DATABASE.exists())
    return {'version':VERSION,'server_time':investments.now_iso(),'database_connected':connected,
            'storage':'PostgreSQL' if hosted else 'SQLite local',
            'previous_backup':storage.backup_metadata(user_id)}
