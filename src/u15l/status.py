"""Read only this firmware's management status; never persist passwords or card IDs."""
import getpass,hashlib,ipaddress,re,secrets,urllib.parse,urllib.request,urllib.error
import xml.etree.ElementTree as ET

def read_status(host):
    if not ipaddress.ip_address(host).is_private:raise RuntimeError('只允许本地私有 IP 管理地址。')
    base='http://'+host+'/'
    op=urllib.request.build_opener(urllib.request.ProxyHandler({}))
    def request(path,headers=None):
        try:r=op.open(urllib.request.Request(base+path,headers=headers or {}),timeout=10)
        except urllib.error.HTTPError as e:r=e
        return r.status,r.headers,r.read().decode(errors='replace')
    _,headers,_=request('login.cgi')
    parts=dict(re.findall(r'(\w+)="([^"]*)"',headers.get('WWW-Authenticate','')))
    if not all(k in parts for k in ('realm','nonce','qop')):raise RuntimeError('登录协议不符。')
    realm,nonce,qop=(parts[k] for k in ('realm','nonce','qop'))
    digest=lambda s:hashlib.sha256(s.encode()).hexdigest()
    password=getpass.getpass('设备管理密码（不显示，也不保存）：')
    ha1=digest('admin:'+realm+':'+digest(password));del password
    def auth(uri,count):
        cn=secrets.token_hex(8);nc=f'{count:08x}'
        response=digest(':'.join([ha1,nonce,nc,cn,qop,digest('GET:'+uri)]))
        h={'Authorization':f'Digest username="admin", realm="{realm}", nonce="{nonce}", uri="{uri}", response="{response}", qop={qop}, nc={nc}, cnonce="{cn}"'}
        return h,cn,response
    h,cn,resp=auth('/cgi/protected.cgi',1)
    query=urllib.parse.urlencode(dict(Action='Digest',username='admin',realm=realm,nonce=nonce,response=resp,qop=qop,cnonce=cn,temp='asr'))
    _,_,body=request('login.cgi?'+query,auth('/cgi/xml_action.cgi',1)[0])
    if '200 OK' not in body:raise RuntimeError('登录失败，停止，不自动重试密码。')
    replies=[]
    for count,name in enumerate(('status1','new_message_report','firmware'),2):
        _,_,body=request('xml_action.cgi?'+urllib.parse.urlencode(dict(method='get',module='duster',file=name)),auth('/cgi/xml_action.cgi',count)[0])
        if 'UNAUTHORIZED' in body or 'KICKOFF' in body:raise RuntimeError('管理会话失效。')
        replies.append(ET.fromstring(body))
    status,msg,fw=replies
    value=lambda k:status.findtext('.//'+k)
    ipv4=value('pdp_context_list/Item/ipv4')
    return {'firmware':fw.findtext('.//sc_sw_outver'),'sim_status':value('sim_status'),'pin_status':value('pin_status'),
            'sim_not_match':msg.findtext('.//sim_not_match'),'operator':value('network_name'),
            'lte_band':value('LTE/band'),'pdp_success':value('pdp_context_list/Item/success'),
            'ipv4_assigned':bool(ipv4 and ipv4 not in ('NA','0.0.0.0')),
            'client_internet_test':'请用手机连接该 Wi-Fi、关闭蜂窝数据后打开未缓存网页；不能仅凭此状态认定完成。'}
