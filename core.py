import csv, io, json, math, secrets, hashlib, hmac, time, uuid
from contextlib import contextmanager
class APIError(Exception):
    def __init__(self,status,message):self.status,self.message=status,message

def hash_password(password):
    salt=secrets.token_hex(16);digest=hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),310000).hex();return salt+':'+digest

def check_password(password, stored):
    salt,digest=stored.split(':');return hmac.compare_digest(hashlib.pbkdf2_hmac('sha256',password.encode(),salt.encode(),310000).hex(),digest)

def number(value, low, high, name):
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value) or not low<=value<=high:raise APIError(400,'Valor inválido: '+name)
    return float(value)

class Service:
    def __init__(self,db,admin_password):
        self.db=db;self.tokens={};self.login_attempts={}
        with self.tx():
            if not db.one('SELECT id FROM usuario WHERE nombre=?',('admin',)):db.execute('INSERT INTO usuario(nombre,password_hash,rol) VALUES(?,?,?)',('admin',hash_password(admin_password),'administrador'))
            if not db.one('SELECT id FROM dispositivo WHERE id=?',('esp32-01',)):db.execute('INSERT INTO dispositivo(id) VALUES(?)',('esp32-01',))
            for key,value in [('temp_max_c','42'),('inactividad_s','60')]:
                if not db.one('SELECT clave FROM configuracion WHERE clave=?',(key,)):db.execute('INSERT INTO configuracion VALUES(?,?)',(key,value))
    @contextmanager
    def tx(self):
        with self.db.lock:
            try:yield;self.db.conn.commit()
            except Exception:self.db.conn.rollback();raise
    def audit(self,user,action,detail=''):self.db.execute('INSERT INTO auditoria(usuario,accion,detalle,creado) VALUES(?,?,?,?)',(user,action,detail,time.time()))
    def session(self,sid):
        s=self.db.one('SELECT s.*,p.residente_id,p.modo,p.objetivo_l,r.codigo FROM sesion s JOIN programacion p ON p.id=s.programacion_id JOIN residente r ON r.id=p.residente_id WHERE s.id=?',(sid,))
        if not s:raise APIError(404,'Sesión no encontrada')
        return s
    def command(self,s,action,extra=None):
        cid=str(uuid.uuid4());now=time.time();payload={'command_id':cid,'session_id':s['id'],'action':action,'expires_at':int(now+90),**(extra or {})}
        self.db.execute('INSERT INTO comando(id,sesion_id,dispositivo_id,accion,payload,estado,creado,expira) VALUES(?,?,?,?,?,?,?,?)',(cid,s['id'],s['dispositivo_id'],action,json.dumps(payload),'pendiente',now,now+90));return cid
    def alert(self,sid,kind,detail):
        if not self.db.one('SELECT id FROM alerta WHERE sesion_id=? AND tipo=?',(sid,kind)):self.db.execute('INSERT INTO alerta(sesion_id,tipo,detalle,creado) VALUES(?,?,?,?)',(sid,kind,detail,time.time()))
    def ingest(self,device,kind,p):
        """Same contract for the broker and local simulator; never sum cumulative volume."""
        with self.tx():
            if not self.db.one('SELECT id FROM dispositivo WHERE id=?',(device,)):raise APIError(403,'Dispositivo no registrado')
            self.db.execute('UPDATE dispositivo SET last_seen=? WHERE id=?',(time.time(),device))
            if kind=='status':
                if p.get('online') is False:self.db.execute('UPDATE dispositivo SET last_seen=NULL WHERE id=?',(device,))
                return {'ok':True}
            if kind=='ack':
                c=self.db.one('SELECT * FROM comando WHERE id=? AND dispositivo_id=?',(p.get('command_id'),device))
                if not c:raise APIError(400,'Comando desconocido')
                # An expired command remains expired; never resurrect it on late ACK.
                if c['estado']!='pendiente' or c['expira']<time.time():return {'ok':True}
                state='confirmado' if p.get('ok') is True else 'rechazado';self.db.execute('UPDATE comando SET estado=? WHERE id=?',(state,c['id']))
                s=self.session(c['sesion_id'])
                if state=='confirmado' and c['accion']=='prepare' and s['estado']=='preparando':self.db.execute('UPDATE sesion SET estado=? WHERE id=?',('preparada',s['id']))
                if state=='rechazado':self.alert(s['id'],'comando_rechazado',str(p.get('reason','rechazado'))[:200])
                return {'ok':True}
            if kind!='telemetry':raise APIError(400,'Tipo de mensaje inválido')
            s=self.session(p.get('session_id'));sid=s['id']
            if s['dispositivo_id']!=device:raise APIError(403,'Dispositivo diferente al programado')
            seq=p.get('seq');boot=p.get('boot_id');state=p.get('state')
            if not isinstance(seq,int) or isinstance(seq,bool) or not 0<=seq<=100000 or not isinstance(boot,str) or not 1<=len(boot)<=40 or state not in ['activa','pausa','finalizada']:raise APIError(400,'Secuencia o estado inválido')
            ack={'session_id':sid,'seq':seq}
            if self.db.one('SELECT id FROM medicion WHERE sesion_id=? AND seq=?',(sid,seq)):return ack
            # Older samples can be kept after finalization; never reopen a finished session.
            if s['estado'] in ['cancelada','error']:raise APIError(409,'Sesión cancelada o vencida')
            flow=number(p.get('flow_l_min'),0,100,'caudal');volume=number(p.get('volume_l'),0,5000,'volumen');elapsed=number(p.get('elapsed_s'),0,86400,'duración')
            temp=p.get('temperature_c')
            pauses=p.get('pauses',0)
            if type(pauses)!=int or not 0<=pauses<=10000:raise APIError(400,'Pausas inválidas')
            if temp is not None:temp=number(temp,-10,100,'temperatura')
            if s['boot_id'] and s['boot_id']!=boot:
                self.alert(sid,'reinicio','Reinicio del ESP32 durante la sesión');self.db.execute('UPDATE sesion SET calidad=? WHERE id=?',('reinicio',sid));return ack
            if seq>s['ultima_seq'] and (volume<s['volumen_l'] or elapsed<s['duracion_s']):raise APIError(409,'Volumen o tiempo acumulado retrocede')
            self.db.execute('INSERT INTO medicion(sesion_id,seq,boot_id,recibido,elapsed_s,caudal_l_min,volumen_l,temperatura_c,estado) VALUES(?,?,?,?,?,?,?,?,?)',(sid,seq,boot,time.time(),elapsed,flow,volume,temp,state))
            if temp is None:self.alert(sid,'sensor_temperatura','DS18B20 sin lectura válida')
            elif temp>float(self.db.one('SELECT valor FROM configuracion WHERE clave=?',('temp_max_c',))['valor']):self.alert(sid,'temperatura_alta','Temperatura superior al umbral configurado')
            if p.get('buffer_overflow'):self.alert(sid,'perdida_datos','Cola del dispositivo llena; sesión excluida del reporte válido');self.db.execute('UPDATE sesion SET calidad=? WHERE id=?',('incompleta',sid))
            if seq>s['ultima_seq']:
                quality=self.session(sid)['calidad'];quality='valida' if quality=='pendiente' else quality
                # Terminal records may arrive before older queued samples.
                final=s['estado']=='finalizada' or state=='finalizada'
                now=time.time();start=s['inicio'] if s['inicio'] is not None else now-elapsed
                self.db.execute('UPDATE sesion SET estado=?,inicio=?,fin=?,volumen_l=?,duracion_s=?,pausas=?,ultima_seq=?,boot_id=?,calidad=? WHERE id=?',('finalizada' if final else state,start,(s['fin'] or now) if final else None,volume,elapsed,pauses,seq,boot,quality,sid))
            current=self.session(sid)
            if current['estado']=='finalizada' and current['calidad'] in ['valida','pendiente_lecturas']:
                count=self.db.one('SELECT COUNT(*) n FROM medicion WHERE sesion_id=?',(sid,))['n']
                self.db.execute('UPDATE sesion SET calidad=? WHERE id=?',('valida' if count==current['ultima_seq']+1 else 'pendiente_lecturas',sid))
            return ack
    def pending(self):
        with self.tx():
            now=time.time()
            expired=self.db.all('SELECT * FROM comando WHERE estado=? AND expira<?',('pendiente',now))
            for c in expired:
                self.db.execute('UPDATE comando SET estado=? WHERE id=?',('vencido',c['id']))
                self.alert(c['sesion_id'],'comando_vencido','Orden sin confirmación en 90 segundos')
                if c['accion']=='prepare':self.db.execute('UPDATE sesion SET estado=?,calidad=? WHERE id=? AND estado=?',('error','incompleta',c['sesion_id'],'preparando'))
            return self.db.all('SELECT * FROM comando WHERE estado=? AND expira>? AND ultimo_envio<?',('pendiente',now,now-3))
    def dispatch(self,method,path,body=None,token=None):
        body=body or {}
        with self.tx():
            if path=='/api/v1/auth/login' and method=='POST':
                name=str(body.get('nombre',''))[:60];now=time.time();attempts=self.login_attempts.get(name,[]);attempts=[t for t in attempts if now-t<300]
                if len(attempts)>=8:raise APIError(429,'Espere cinco minutos antes de reintentar')
                u=self.db.one('SELECT * FROM usuario WHERE nombre=? AND activo=1',(name,))
                if not u or not check_password(str(body.get('password','')),u['password_hash']):self.login_attempts[name]=attempts+[now];raise APIError(401,'Credenciales incorrectas')
                self.login_attempts.pop(name,None);tok=secrets.token_urlsafe(32);self.tokens[tok]={'nombre':u['nombre'],'rol':u['rol'],'expires':now+28800};return 200,{'token':tok,'nombre':u['nombre'],'rol':u['rol']}
            user=self.tokens.get(token)
            if not user or user['expires']<time.time():raise APIError(401,'Inicie sesión')
            if path=='/api/v1/auth/logout':self.tokens.pop(token,None);return 200,{'ok':True}
            name=user['nombre'];admin=user['rol']=='administrador';parts=path.split('/')
            if path in ['/api/v1/usuarios','/api/v1/configuracion'] and method!='GET' and not admin:raise APIError(403,'Solo el administrador')
            if path=='/api/v1/usuarios':
                if not admin:raise APIError(403,'Solo el administrador')
                if method=='GET':return 200,self.db.all('SELECT id,nombre,rol,activo FROM usuario')
                username=str(body.get('nombre',''));password=str(body.get('password',''));role=body.get('rol')
                if not 3<=len(username)<=60 or len(password)<12 or role not in ['administrador','moderador']:raise APIError(400,'Cuenta inválida; contraseña mínima de 12 caracteres')
                self.db.execute('INSERT INTO usuario(nombre,password_hash,rol) VALUES(?,?,?)',(username,hash_password(password),role));self.audit(name,'crear_usuario',username);return 201,{'ok':True}
            if path=='/api/v1/residentes':
                if method=='GET':return 200,self.db.all('SELECT * FROM residente ORDER BY codigo')
                import re
                code=str(body.get('codigo',''))
                if not re.fullmatch('[A-Za-z0-9_-]{1,24}',code):raise APIError(400,'Use un código seudónimo de hasta 24 caracteres')
                self.db.execute('INSERT INTO residente(codigo) VALUES(?)',(code,));self.audit(name,'crear_residente',code);return 201,{'ok':True}
            if path=='/api/v1/dispositivos':return 200,self.db.all('SELECT * FROM dispositivo')
            if path=='/api/v1/configuracion':
                if method=='GET':return 200,{r['clave']:r['valor'] for r in self.db.all('SELECT * FROM configuracion')}
                for key,low,high in [('temp_max_c',30,45),('inactividad_s',30,300)]:
                    if key in body:self.db.execute('UPDATE configuracion SET valor=? WHERE clave=?',(str(number(body[key],low,high,key)),key))
                self.audit(name,'configuracion',json.dumps(body));return 200,{'ok':True,'nota':'Se aplicará a las próximas sesiones; umbral técnico de laboratorio'}
            if path=='/api/v1/sesiones/preparar' and method=='POST':
                r=self.db.one('SELECT * FROM residente WHERE id=? AND activo=1',(body.get('residente_id'),));dev=body.get('dispositivo_id','esp32-01');mode=body.get('modo')
                if not r or mode not in ['tradicional','inteligente'] or not self.db.one('SELECT id FROM dispositivo WHERE id=?',(dev,)):raise APIError(400,'Residente, modo o dispositivo inválido')
                if self.db.one("SELECT id FROM sesion WHERE dispositivo_id=? AND estado NOT IN ('finalizada','cancelada','error')",(dev,)):raise APIError(409,'El dispositivo tiene una sesión pendiente')
                goal=number(body.get('objetivo_l',40),1,500,'objetivo');pid=str(uuid.uuid4());sid=str(uuid.uuid4())
                self.db.execute('INSERT INTO programacion VALUES(?,?,?,?,?)',(pid,r['id'],mode,goal,time.time()))
                self.db.execute('INSERT INTO objetivo_consumo VALUES(?,?,?,?,?)',(str(uuid.uuid4()),pid,goal,'manual',time.time()))
                self.db.execute('INSERT INTO sesion(id,programacion_id,dispositivo_id,estado) VALUES(?,?,?,?)',(sid,pid,dev,'preparando'))
                config={x['clave']:float(x['valor']) for x in self.db.all('SELECT * FROM configuracion')}
                cid=self.command(self.session(sid),'prepare',{'mode':mode,'goal_l':goal,'temp_max_c':config['temp_max_c'],'idle_s':config['inactividad_s']});self.audit(name,'preparar',sid);return 202,{'id':sid,'command_id':cid,'estado':'preparando'}
            if path=='/api/v1/sesiones':return 200,self.db.all('SELECT s.*,r.codigo,p.modo,p.objetivo_l FROM sesion s JOIN programacion p ON p.id=s.programacion_id JOIN residente r ON r.id=p.residente_id ORDER BY p.creado DESC LIMIT 200')
            if len(parts)>=5 and parts[3]=='sesiones':
                sid=parts[4];s=self.session(sid)
                if len(parts)==5:return 200,s
                if parts[5]=='lecturas':return 200,self.db.all('SELECT * FROM medicion WHERE sesion_id=? ORDER BY seq DESC LIMIT 300',(sid,))
                if parts[5]=='cancelar' and method=='POST':
                    if s['estado'] not in ['preparando','preparada','error']:raise APIError(409,'Solo cancelar preparaciones sin lectura; para una ducha activa solicite detener')
                    if self.db.one('SELECT id FROM medicion WHERE sesion_id=?',(sid,)):raise APIError(409,'Sesión con mediciones')
                    # Confirm stop/disarm too: do not free device until ESP reports termination.
                    cid=self.command(s,'stop');self.audit(name,'cancelar',sid);return 202,{'command_id':cid,'estado':'pendiente'}
                if parts[5]=='detener' and method=='POST':
                    if s['estado'] in ['finalizada','cancelada','error']:raise APIError(409,'La sesión ya terminó')
                    existing=self.db.one("SELECT id FROM comando WHERE sesion_id=? AND accion='stop' AND estado='pendiente'",(sid,))
                    cid=existing['id'] if existing else self.command(s,'stop');self.audit(name,'detener',sid);return 202,{'command_id':cid,'estado':'pendiente','mensaje':'Esperando confirmación y telemetría final del dispositivo'}
            if path=='/api/v1/comandos':return 200,self.db.all('SELECT id,sesion_id,accion,estado,creado,expira FROM comando ORDER BY creado DESC LIMIT 50')
            if path=='/api/v1/alertas':return 200,self.db.all('SELECT * FROM alerta ORDER BY creado DESC LIMIT 100')
            if len(parts)==5 and parts[3]=='alertas' and method=='PATCH':
                if not self.db.one('SELECT id FROM alerta WHERE id=?',(parts[4],)):raise APIError(404,'Alerta inexistente')
                self.db.execute('UPDATE alerta SET atendida=1,responsable=? WHERE id=?',(name,parts[4]));self.audit(name,'atender_alerta',parts[4]);return 200,{'ok':True}
            if path=='/api/v1/reportes/comparacion':
                rows=self.db.all("SELECT r.codigo,p.modo,AVG(s.volumen_l) media_l,COUNT(*) n FROM sesion s JOIN programacion p ON p.id=s.programacion_id JOIN residente r ON r.id=p.residente_id WHERE s.estado='finalizada' AND s.calidad='valida' GROUP BY r.codigo,p.modo")
                out={}
                for x in rows:out.setdefault(x['codigo'],{'codigo':x['codigo']})[x['modo']]=x
                for x in out.values():
                    a=x.get('tradicional',{}).get('media_l');b=x.get('inteligente',{}).get('media_l');x['reduccion_pct']=100*(a-b)/a if a and b is not None else None
                return 200,list(out.values())
            if path=='/api/v1/exportaciones':
                rows=self.db.all('SELECT r.codigo,p.modo,s.id,s.estado,s.calidad,s.volumen_l,s.duracion_s,s.pausas FROM sesion s JOIN programacion p ON p.id=s.programacion_id JOIN residente r ON r.id=p.residente_id ORDER BY p.creado')
                buf=io.StringIO();w=csv.DictWriter(buf,fieldnames=['codigo','modo','id','estado','calidad','volumen_l','duracion_s','pausas']);w.writeheader();w.writerows(rows);self.audit(name,'exportar_csv');return 200,buf.getvalue()
            if path=='/api/v1/auditoria':
                if not admin:raise APIError(403,'Solo el administrador')
                return 200,self.db.all('SELECT * FROM auditoria ORDER BY creado DESC LIMIT 100')
            if path=='/api/v1/predicciones':return 200,{'estado':'pendiente_entrenamiento','mensaje':'No hay modelo de IA entrenado. El objetivo se registra manualmente y no se presenta como predicción.'}
            if path=='/api/v1/encuestas' and method=='POST':
                answers=body.get('respuestas');moment=body.get('momento')
                if not self.db.one('SELECT id FROM residente WHERE id=?',(body.get('residente_id'),)) or moment not in ['pre','post'] or not isinstance(answers,list) or len(answers)!=3 or any(type(x)!=int or not 1<=x<=5 for x in answers):raise APIError(400,'Encuesta inválida: tres respuestas Likert de 1 a 5')
                self.db.execute('INSERT INTO encuesta(residente_id,momento,respuestas,creado) VALUES(?,?,?,?)',(body['residente_id'],moment,json.dumps(answers),time.time()));return 201,{'ok':True}
            raise APIError(404,'Ruta no disponible')
