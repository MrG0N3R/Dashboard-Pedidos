import fdb

fdb.load_api(r"C:\Program Files\Firebird\Firebird_3_0\fbclient.dll")
conn = fdb.connect(
    dsn='192.168.100.1:D:\\Microsip datos\\UGRPG DAB.FDB',
    user='SYSDBA',
    password='mirra19',
    charset='NONE'
)

print("Conectado OK")
conn.close()