"""Shadow Lord Rising installer. Builds recipient-specific patches, never ships campaign archives."""
from __future__ import annotations
import argparse,copy,datetime,hashlib,json,os,re,shutil,struct,subprocess,sys,tempfile,traceback
from pathlib import Path
if not getattr(sys,'frozen',False):
 local=Path(__file__).parent/'vendor'
 if local.exists():sys.path.insert(0,str(local))
 # Development path is not used by the frozen installer or required by players.
 elif Path('D:/Maul dev/Install_20260925/tools').exists():sys.path.insert(0,'D:/Maul dev/Install_20260925/tools')
from pykotor.resource.formats.twoda import read_2da as _read_2da,bytes_2da,TwoDA
from pykotor.resource.formats.gff import read_gff,bytes_gff,GFFStruct,GFFList,GFFFieldType
from pykotor.resource.formats.erf import read_erf,bytes_erf,ERF,ERFType
from pykotor.resource.formats.rim import read_rim
from pykotor.resource.formats.tlk import read_tlk,bytes_tlk
from pykotor.resource.formats.ncs import compile_nss,bytes_ncs,read_ncs
from pykotor.resource.type import ResourceType
from pykotor.common.misc import Game,ResRef
from pykotor.common.language import LocalizedString,Language

VERSION='0.1.0-test'
MARKER='ShadowLordRising-install.json'
class InstallError(RuntimeError):pass
def digest(data):return hashlib.sha256(data).hexdigest()
def jread(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def rows(table):return [{h:r.get_string(h) for h in table.get_headers()} for r in table]
def read_2da(source):
 data=source if isinstance(source,bytes) else Path(source).read_bytes()
 if not data.startswith(b'2DA V2.b\n'):return _read_2da(data)
 # Some shipped/mod tables have a zero pool-size field despite valid strings
 # following it. The engine follows cell offsets; read them the same way.
 end=data.index(b'\0',9);headers=data[9:end].decode('ascii').rstrip('\t').split('\t');pos=end+1
 count=struct.unpack_from('<I',data,pos)[0];pos+=4;labels=[]
 for _ in range(count):
  end=data.index(b'\t',pos);labels.append(data[pos:end].decode('ascii'));pos=end+1
 start=pos+2*count*len(headers)+2;t=TwoDA(headers)
 if start>len(data):raise InstallError('Truncated 2DA table.')
 for i,label in enumerate(labels):
  fields={}
  for j,h in enumerate(headers):
   offset=struct.unpack_from('<H',data,pos+2*(i*len(headers)+j))[0];at=start+offset
   if at>=len(data):raise InstallError('2DA cell points outside string pool.')
   fields[h]=data[at:data.index(b'\0',at)].decode('cp1252')
  t.add_row(label,fields)
 return t
def ci(folder,name):
 p=folder/name
 if p.exists():return p
 if folder.exists():
  for x in folder.iterdir():
   if x.name.lower()==name.lower():return x
 return p
def compile_script(src):
 data=bytes_ncs(compile_nss(src,Game.K2));read_ncs(data);return data

class Installer:
 def __init__(self,game,package,allow_workshop=False):
  self.game=Path(game).resolve();self.package=Path(package).resolve();self.payload=self.package/'payload'
  self.spec=jread(self.payload/'spec.json');self.full=self.spec['edition']=='Full'
  self.override=ci(self.game,'Override');self.modules=ci(self.game,'Modules')
  self.pending={};self.input_hashes={};self.notes=[];self.report={'version':VERSION,'edition':self.spec['edition'],'patched_modules':[],'placements':[],'inline_nodes':0,'tlk_changes':0}
  self.allow_workshop=allow_workshop;self.native_index=None;self.module_cache={}
 def existing(self,path):
  path=Path(path);data=path.read_bytes() if path.exists() else None
  self.input_hashes[path]=digest(data) if data is not None else None
  return data
 def queue(self,path,data):
  path=Path(path).resolve()
  if not path.is_relative_to(self.game):raise InstallError('Refusing write outside the chosen game directory.')
  if path not in self.input_hashes:self.existing(path)
  if self.input_hashes[path]!=digest(data):self.pending[path]=data
 def native(self,name,typ):
  if self.native_index is None:
   raw=(self.game/'chitin.key').read_bytes();nf,nk,fo,ko=struct.unpack_from('<4I',raw,8);files=[]
   for i in range(nf):
    _,no,nl,_=struct.unpack_from('<IIHH',raw,fo+i*12);files.append(self.game/raw[no:no+nl].split(b'\0')[0].decode().replace('\\','/'))
   self.native_index={}
   for i in range(nk):
    p=ko+i*22;n=raw[p:p+16].split(b'\0')[0].decode().lower();t,rid=struct.unpack_from('<HI',raw,p+16);self.native_index[(n,t)]=(files[rid>>20],rid&0xfffff)
  try:path,index=self.native_index[(name.lower(),typ)]
  except KeyError:raise InstallError(f'Required game resource missing: {name} ({typ})')
  with path.open('rb') as f:
   header=f.read(20);vo=struct.unpack_from('<I',header,16)[0];f.seek(vo+index*16);_,off,size,_=struct.unpack('<4I',f.read(16));f.seek(off);return f.read(size)
 def effective(self,name,typ):
  p=ci(self.override,name+'.'+ResourceType.from_id(typ).extension)
  return self.existing(p) if p.exists() else self.native(name,typ)
 def table(self,name):return read_2da(self.effective(name,2017))
 def check_package(self):
  manifest=jread(self.package/'payload-manifest.json')
  for rel,h in manifest.items():
   p=(self.package/rel).resolve()
   if not p.is_relative_to(self.package) or not p.is_file() or digest(p.read_bytes())!=h:raise InstallError('Package is incomplete or modified: '+rel)
 def preflight(self):
  if not (self.game/'chitin.key').is_file() or not (self.game/'swkotor2.exe').is_file():raise InstallError('Choose the KOTOR II folder containing swkotor2.exe and chitin.key.')
  if not self.modules.is_dir():raise InstallError('The game Modules directory is missing.')
  if self.full and not ci(self.modules,'003ebo.mod').exists():raise InstallError('The Full edition requires a manual TSLRCM installation. Its cargo-hold item locations are not present in the vanilla module. Install TSLRCM first, or choose Maul-Progression only.')
  if (self.game/MARKER).exists():raise InstallError('Shadow Lord Rising is already installed here. Use Uninstall before changing editions or reinstalling.')
  if ci(self.override,'mp_sync.ncs').exists() or ci(self.override,'slr_sync.ncs').exists():raise InstallError('An older development/progression install is present. Use a clean game installation; do not overwrite the development setup.')
  if self.override.exists() and any(p.suffix.lower() in ['.are','.ifo'] for p in self.override.iterdir()):raise InstallError('Loose area/module templates in Override need a compatibility patch. No files have been changed.')
  if os.name=='nt':
   running=subprocess.run(['tasklist','/FI','IMAGENAME eq swkotor2.exe','/NH'],capture_output=True,text=True,check=True).stdout
   if 'swkotor2.exe' in running.lower():raise InstallError('Close KOTOR II before installing.')
  workshop=self.game.parent.parent/'workshop/content/208580'
  detected=[]
  if workshop.is_dir():
   for folder in workshop.iterdir():
    if folder.is_dir() and (any(ci(ci(folder,'Override'),n+'.2da').exists() for n in ['appearance','heads','portraits','globalcat']) or ci(folder,'Modules').is_dir()):detected.append(folder.name)
  if detected and not self.allow_workshop:raise InstallError('Workshop gameplay folders detected ('+', '.join(detected)+'). This test installer supports manual installs. See README: do not install across Workshop gameplay mods. If these folders are inactive leftovers, --inactive-workshop bypasses this check without changing them.')
  self.check_package()
  tlk=read_tlk(self.game/'dialog.tlk')
  if tlk.language!=Language.ENGLISH:raise InstallError('This test release supports the English game only.')
  self.report['language']='English';self.report['workshop_leftovers_bypassed']=bool(detected)
  return tlk
 def append(self,t,data):return t.add_row(str(t.get_height()),{h:data.get(h,'') for h in t.get_headers()})
 def tables_and_assets(self):
  ap=self.table('appearance');heads=self.table('heads');por=self.table('portraits');glob=self.table('globalcat')
  for t,key,values in [(heads,'head',['p_maul_cwh','mp_hd_d1']),(ap,'label',['P_MAUL_GORGET_WRAPS','SLR_DONOR_N'])]:
   if any(r.get_string(key).lower() in [v.lower() for v in values] for r in t):raise InstallError('Existing Maul/Shadow Lord table entries detected; clean installation required.')
  if ap.get_height()<=168:raise InstallError('Unsupported appearance table: PMHC01 player slots missing.')
  portrait_matches=[i for i,r in enumerate(por) if r.get_string('appearancenumber')=='167' and r.get_string('appearance_s')=='166' and r.get_string('appearance_l')=='168']
  if len(portrait_matches)!=1:raise InstallError('Cannot safely identify the original PMHC01 portrait slot.')
  self.headids=[self.append(heads,h) for h in self.spec['heads']]
  for index in [166,167,168]:
   r=ap.get_row(index);source=self.spec['base_appearances'][str(index)]
   # Replace only this character slot and its unclothed body. Other slots and
   # armor models remain recipient-specific.
   for k in ['label','modela','texa']+(['modelb','texb'] if self.full else []):r.set_string(k,source[k])
   r.set_string('normalhead',str(self.headids[0]));r.set_string('backuphead',str(self.headids[0]))
  self.allowed=[166,167,168]
  if self.full:
   g=dict(self.spec['gorget_appearance']);g['normalhead']=g['backuphead']=str(self.headids[0]);g['label']='SLR_GORGET_WRAPS'
   self.gorgetid=self.append(ap,g);self.allowed.append(self.gorgetid)
  self.donors=[]
  for stage,code in enumerate(['N','D1','D2','D3','L1','L2','L3']):
   donor={h:ap.get_row(166).get_string(h) for h in ap.get_headers()};donor.update(label='SLR_DONOR_'+code,normalhead=str(self.headids[stage]),backuphead=str(self.headids[stage]),portrait='po_MPr'+code)
   self.donors.append(self.append(ap,donor))
  p=por.get_row(portrait_matches[0])
  for k,v in self.spec['portrait'].items():
   if k in ['baseresref','baseresrefe','baseresrefve','baseresrefvve','baseresrefvvve']:p.set_string(k,v)
  for name,typ in [('SLR_EPOCH','Number'),('SLR_STATE','String')]:
   if any(r.get_string('name').lower()==name.lower() for r in glob):raise InstallError('Progression global already exists: '+name)
   self.append(glob,{'name':name,'type':typ})
  for name,t in [('appearance',ap),('heads',heads),('portraits',por),('globalcat',glob)]:self.queue(self.override/(name+'.2da'),bytes_2da(t))
  for asset in (self.payload/'assets').iterdir():
   data=asset.read_bytes();dst=ci(self.override,asset.name)
   if dst.exists() and dst.read_bytes()!=data:raise InstallError('Conflicting asset already exists: '+asset.name)
   if self.full and asset.suffix.lower()=='.uti' and asset.stem in ['maul_gorget','maul_gorget_m']:
    g=read_gff(data)
    props=g.root.get_list('PropertiesList')
    for prop in props:
     if prop.get_uint16('PropertyName')==59:prop.set_uint16('Subtype',self.gorgetid)
    g.root.set_list('PropertiesList',props)
    data=bytes_gff(g)
   self.queue(dst,data)
  if self.full:
   table=self.table('upcrystals')
   for data in self.spec['crystals']:
    if any(r.get_string('template').lower()==data['template'].lower() for r in table):raise InstallError('Color crystal already installed: '+data['template'])
    self.append(table,data)
   self.queue(self.override/'upcrystals.2da',bytes_2da(table))
   # Namespaced model slots must not silently replace another author's weapon.
   for name in ['w_lghtsbr_255.mdl']:
    p=ci(self.override,name)
    if p.exists() and digest(p.read_bytes())!=digest((self.payload/'assets'/ci(self.payload/'assets',name).name).read_bytes()):raise InstallError('Weapon model slot conflict: '+name)
  self.report.update(head_rows=self.headids,donor_appearances=self.donors,allowed_appearances=self.allowed,portrait_row=portrait_matches[0])
 def runtime(self):
  allowed=' || '.join('appearance == '+str(i) for i in self.allowed)
  select='int headAppearance = '+str(self.donors[0])+';\n'+''.join('if (stage == '+str(i)+') headAppearance = '+str(self.donors[i])+';\n' for i in range(1,7))
  sync='''void main() {
object pc=GetFirstPC(); if (!GetIsObjectValid(pc) || GetIsConversationActive()) return;
int appearance=GetAppearanceType(pc); if (!(ALLOWED)) return;
int alignment=GetGoodEvilValue(pc); if (alignment<0 || alignment>100) return;
int stage=0;
if (alignment<=40) stage=1; if (alignment<=20) stage=2; if (alignment<=10) stage=3;
if (alignment>=60) stage=4; if (alignment>=80) stage=5; if (alignment>=90) stage=6;
object donor=CreateObject(OBJECT_TYPE_CREATURE,"slr_headwatch",GetLocation(pc));
if (!GetIsObjectValid(donor)) return;
SELECT
ChangeObjectAppearance(donor,headAppearance); DuplicateHeadAppearance(pc,donor);
SetGlobalString("SLR_STATE",IntToString(stage)); DestroyObject(donor);
}'''.replace('ALLOWED',allowed).replace('SELECT',select)
  start='''void main() {
object pc=GetFirstPC(); int attempt=GetScriptParameter(1); if (attempt<0 || attempt>12) attempt=0;
if (!GetIsObjectValid(pc)) { if (attempt<12) DelayCommand(1.0,ExecuteScript("slr_start",GetModule(),attempt+1)); return; }
int appearance=GetAppearanceType(pc);
if (!(ALLOWED)) { if (attempt<12) DelayCommand(1.0,ExecuteScript("slr_start",GetModule(),attempt+1)); return; }
int token=GetGlobalNumber("SLR_EPOCH")+1; if (token>255) token=1;
SetGlobalNumber("SLR_EPOCH",token); ExecuteScript("slr_sync",pc);
DelayCommand(2.0,ExecuteScript("slr_tick",pc,token));
}'''.replace('ALLOWED',allowed)
  tick='''void main() { int token=GetScriptParameter(1); if (token!=GetGlobalNumber("SLR_EPOCH")) return;
ExecuteScript("slr_sync",OBJECT_SELF); DelayCommand(2.0,ExecuteScript("slr_tick",OBJECT_SELF,token)); }'''
  for name,src in [('slr_sync',sync),('slr_start',start),('slr_tick',tick)]:self.queue(self.override/(name+'.ncs'),compile_script(src))
  g=read_gff(self.payload/'headwatch.utc');g.root.set_resref('TemplateResRef',ResRef('slr_headwatch'));g.root.set_string('Tag','slr_headwatch');g.root.set_uint16('Appearance_Type',self.donors[0]);self.queue(self.override/'slr_headwatch.utc',bytes_gff(g))
 def module_names(self):
  result=set()
  for p in self.modules.iterdir():
   if p.suffix.lower() in ['.rim','.mod']:
    name=p.stem.lower()
    if name.endswith('_s'):name=name[:-2]
    if re.fullmatch(r'[0-9]{3}[a-z0-9]+',name):result.add(name)
  return sorted(result)
 def module(self,name):
  if name in self.module_cache:return self.module_cache[name]
  mod=ci(self.modules,name+'.mod');resources={}
  dialogue=ci(self.modules,name+'_dlg.erf')
  if dialogue.exists():
   for r in read_erf(self.existing(dialogue)):resources[(str(r.resref).lower(),r.restype)]=r.data
  if mod.exists():
   archive=read_erf(self.existing(mod));resources.update({(str(r.resref).lower(),r.restype):r.data for r in archive})
  else:
   for suffix in ['.rim','_s.rim']:
    p=ci(self.modules,name+suffix)
    if p.exists():
     for r in read_rim(self.existing(p)):resources[(str(r.resref).lower(),r.restype)]=r.data
  self.module_cache[name]=(mod,resources);return mod,resources
 def replace_inline(self,g,mapping):
  count=0
  def visit(st):
   nonlocal count
   for label,typ,value in list(st):
    if typ==GFFFieldType.LocalizedString:
     for language,gender,text in list(value):
      if language==Language.ENGLISH and text in mapping:value.set_data(language,gender,mapping[text]);count+=1
    elif typ==GFFFieldType.Struct:visit(value)
    elif typ==GFFFieldType.List:
     for child in value:visit(child)
  visit(g.root);return count
 def add_items(self,resources,resref,typ,items,location):
  key=(resref,typ)
  # Respect existing loose templates: they override the module's resources.
  loose=ci(self.override,resref+'.'+typ.extension)
  raw=self.pending.get(loose) or (self.existing(loose) if loose.exists() else resources.get(key))
  if raw is None:raise InstallError('Required campaign inventory missing: '+location)
  g=read_gff(raw);inventory=g.root.get_list('ItemList')
  if inventory is None:raise InstallError('Unexpected inventory format: '+location)
  current={str(x.get_resref('InventoryRes')).lower() for x in inventory}
  for item in items:
   if item not in current:
    ent=inventory.add(0);ent.set_resref('InventoryRes',ResRef(item));ent.set_uint16('Repos_PosX',0);ent.set_uint16('Repos_PosY',len(inventory)-1)
    if typ==ResourceType.UTM:ent.set_uint8('Infinite',1)
    else:ent.set_uint8('Dropable',1)
  g.root.set_list('ItemList',inventory)
  data=bytes_gff(g)
  if loose.exists():self.queue(loose,data)
  else:resources[key]=data
  self.report['placements'].append({'location':location,'items':items})
 def patch_modules(self):
  definitions=jread(self.payload/'dialogue.json') if self.full else None
  locations={'003ebo':('ebcont001',ResourceType.UTP,['maul_gorget'],'Ebon Hawk cargo hold / Handmaiden room'),
             '411dxn':('nadd_reward2',ResourceType.UTP,['nightbrother'],'Freedon Nadd burial chamber'),
             '202tel':('m_202_003',ResourceType.UTM,['maul_gorget'],'Telos merchant'),
             '602dan':('store_adum',ResourceType.UTM,['maul_gorget'],'Adum on Dantooine')}
  names=self.module_names();required=set(locations)|{'403dxn'}
  if self.full and not required.issubset(names):raise InstallError('Required campaign modules missing: '+', '.join(sorted(required-set(names))))
  for name in names:
   path,res=self.module(name);before=dict(res);events=0
   for (ref,typ),raw in list(res.items()):
    if typ not in [ResourceType.ARE,ResourceType.IFO,ResourceType.DLG]:continue
    if typ==ResourceType.DLG:
     if not self.full:continue
     if not any(text.encode('cp1252',errors='replace') in raw for text in definitions['inline']):continue
     g=read_gff(raw);count=self.replace_inline(g,definitions['inline'])
     if count:res[(ref,typ)]=bytes_gff(g);self.report['inline_nodes']+=count
     continue
    g=read_gff(raw);field='OnEnter' if typ==ResourceType.ARE else 'Mod_OnModLoad';original=str(g.root.acquire(field,''))
    if original.lower().startswith('slr_'):raise InstallError('Module already contains a Shadow Lord hook: '+name)
    wrapper='slr_'+hashlib.sha256((name+':'+ref+':'+field).encode()).hexdigest()[:11]
    if ci(self.override,wrapper+'.ncs').exists():raise InstallError('Script name conflict: '+wrapper)
    call='ExecuteScript("'+original+'",OBJECT_SELF,GetScriptParameter(1));' if original else ''
    src='void main() {'+call+' DelayCommand(0.3,ExecuteScript("slr_start",GetModule(),0));}'
    g.root.set_resref(field,ResRef(wrapper));res[(ref,typ)]=bytes_gff(g);res[(wrapper,ResourceType.NCS)]=compile_script(src);events+=1
   if self.full and name in locations:self.add_items(res,*locations[name])
   if self.full and name=='403dxn':
    key=('sarge',ResourceType.DLG);loose=ci(self.override,'sarge.dlg');raw=self.existing(loose) if loose.exists() else res.get(key)
    if raw is None:raise InstallError('Bralor reward dialogue missing.')
    g=read_gff(raw);entries=g.root.get_list('EntryList')
    if len(entries)<=67:raise InstallError('Bralor dialogue is incompatible: final-victory node 67 missing.')
    node=entries[67];original=str(node.acquire('Script',''))
    if original!='a_xp18':raise InstallError('Bralor reward has been modified by another mod; expected a_xp18, found '+original)
    node.set_resref('Script',ResRef('slr_bralorreward'))
    g.root.set_list('EntryList',entries)
    data=bytes_gff(g)
    if loose.exists():self.queue(loose,data)
    else:res[key]=data
    res[('slr_bralorreward',ResourceType.NCS)]=compile_script('void main(){ ExecuteScript("a_xp18",OBJECT_SELF); CreateItemOnObject("jc_darksaber",GetFirstPC(),1); }')
    self.report['placements'].append({'location':'Final Bralor victory dialogue','items':['jc_darksaber'],'preserves':'a_xp18 (1000 XP)'})
   if res!=before:
    archive=ERF(ERFType.MOD)
    for (ref,typ),data in res.items():archive.set_data(ref,typ,data)
    payload=bytes_erf(archive);reparsed={(str(r.resref).lower(),r.restype):r.data for r in read_erf(payload)}
    if reparsed!=res:raise InstallError('Module round-trip validation failed: '+name)
    # Every unrelated resource must remain byte-identical.
    changed=[ref+'.'+typ.extension for (ref,typ),data in before.items() if res.get((ref,typ))!=data]
    self.queue(path,payload);self.report['patched_modules'].append({'name':name,'event_hooks':events,'changed_resources':changed})
  if not self.report['patched_modules']:raise InstallError('No playable campaign modules found; progression cannot be installed safely.')
  if self.full:
   # Inline dialogue resources installed loose must also retain precedence.
   for p in self.override.iterdir() if self.override.exists() else []:
    if p.suffix.lower()=='.dlg':
     raw=self.pending.get(p) or self.existing(p)
     if not any(text.encode('cp1252',errors='replace') in raw for text in definitions['inline']):continue
     g=read_gff(raw);count=self.replace_inline(g,definitions['inline'])
     if count:self.queue(p,bytes_gff(g));self.report['inline_nodes']+=count
 def dialogue(self,tlk):
  if not self.full:return
  definitions=jread(self.payload/'dialogue.json');conflicts=[];applied=0;missing=[]
  for number,data in definitions['tlk'].items():
   ent=tlk.get(int(number))
   # References from optional restored/M4-78 content may be absent from vanilla.
   if ent is None:missing.append(int(number));continue
   if ent.text==data['new']:continue
   if ent.text!=data['old']:conflicts.append(int(number));continue
   ent.text=data['new'];applied+=1
  if conflicts:raise InstallError('Dialogue text differs at '+str(conflicts[:12])+'. This release will not overwrite another translation/dialogue mod. See README.')
  self.report['tlk_changes']=applied;self.report['optional_tlk_refs_absent']=missing
  self.queue(self.game/'dialog.tlk',bytes_tlk(tlk))
 def plan(self):
  print('Checking game and package...',flush=True);tlk=self.preflight()
  print('Preparing Maul and alignment progression...',flush=True);self.tables_and_assets();self.runtime()
  print('Merging campaign modules. This may take a few minutes...',flush=True);self.patch_modules();self.dialogue(tlk)
  self.report['files_changed']=len(self.pending);self.report['in_game_verified']=False
  return self.report
 def apply(self):
  # Preflight is complete before creating backups or writing gameplay files.
  for p,before in self.input_hashes.items():
   actual=digest(p.read_bytes()) if p.exists() else None
   if actual!=before:raise InstallError('A game file changed during preparation: '+str(p))
  backup=self.game/'ShadowLordRising_Backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S-%f');backup.mkdir(parents=True)
  manifest={'version':VERSION,'edition':self.spec['edition'],'game':str(self.game),'files':[],'report':self.report}
  staged=backup/'staged';staged.mkdir()
  for i,(p,data) in enumerate(self.pending.items()):
   rel=p.relative_to(self.game).as_posix();old=self.input_hashes[p];bk=backup/'original'/rel
   if old is not None:bk.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(p,bk)
   (staged/str(i)).write_bytes(data);manifest['files'].append({'path':rel,'before':old,'after':digest(data),'backup':str(bk.relative_to(backup)) if old else None,'staged':str(i)})
  mp=backup/'manifest.json';mp.write_text(json.dumps(manifest,indent=2));changed=[]
  try:
   for rec in manifest['files']:
    dst=self.game/rec['path'];dst.parent.mkdir(parents=True,exist_ok=True);changed.append(rec);shutil.copyfile(staged/rec['staged'],dst)
    if digest(dst.read_bytes())!=rec['after']:raise InstallError('Installed hash mismatch: '+rec['path'])
   (self.game/MARKER).write_text(json.dumps({'version':VERSION,'edition':self.spec['edition'],'manifest':str(mp)},indent=2))
  except BaseException:
   for rec in reversed(changed):
    dst=self.game/rec['path']
    if rec['backup']:shutil.copy2(backup/rec['backup'],dst)
    elif dst.exists():dst.unlink()
   raise
  # Keep staged files in the backup: they support recovery if writing is interrupted.
  return mp

def uninstall(game):
 game=Path(game).resolve();marker=game/MARKER
 if not marker.exists():raise InstallError('No Shadow Lord Rising install record found.')
 mp=Path(jread(marker)['manifest']).resolve()
 if not mp.is_relative_to(game/'ShadowLordRising_Backups'):raise InstallError('Invalid backup location.')
 info=jread(mp);backup=mp.parent
 for r in info['files']:
  p=(game/r['path']).resolve()
  if not p.is_relative_to(game):raise InstallError('Invalid restore path.')
  if not p.exists() or digest(p.read_bytes())!=r['after']:raise InstallError('Uninstall stopped: another mod changed '+r['path']+'. Restore the recorded backup manually or remove later mods first.')
  if r['backup']:
   bk=(backup/r['backup']).resolve()
   if not bk.is_relative_to(backup) or not bk.exists() or digest(bk.read_bytes())!=r['before']:raise InstallError('Backup is missing or damaged: '+r['path'])
 for r in reversed(info['files']):
  p=game/r['path']
  if r['backup']:shutil.copy2(backup/r['backup'],p)
  else:p.unlink()
 marker.unlink();return mp

def main():
 parser=argparse.ArgumentParser(description='Shadow Lord Rising '+VERSION+' installer by juggernut')
 parser.add_argument('game',nargs='?');parser.add_argument('--package');parser.add_argument('--uninstall',action='store_true');parser.add_argument('--dry-run',action='store_true');parser.add_argument('--inactive-workshop',action='store_true');parser.add_argument('--report')
 args=parser.parse_args();interactive=args.game is None
 if interactive:
  import tkinter as tk
  from tkinter import filedialog,messagebox
  root=tk.Tk();root.withdraw();args.game=filedialog.askdirectory(title='Select KOTOR II folder (contains swkotor2.exe)')
  if not args.game:return 0
 try:
  if args.uninstall:
   mp=uninstall(args.game);message='Removed Shadow Lord Rising. Original files restored. Backup retained at '+str(mp)
  else:
   package=Path(args.package) if args.package else (Path(sys.executable).parent if getattr(sys,'frozen',False) else Path(__file__).parent)
   inst=Installer(args.game,package,args.inactive_workshop);report=inst.plan()
   if args.report:Path(args.report).write_text(json.dumps(report,indent=2))
   if args.dry_run:print(json.dumps(report,indent=2));return 0
   if interactive and not messagebox.askyesno('Ready to install',f"Shadow Lord Rising {VERSION}\nEdition: {inst.spec['edition']}\nFiles to change: {len(inst.pending)}\n\nBackups will be created. Install now?"):return 0
   mp=inst.apply();message='Installed and hash-verified. Restart KOTOR II. Begin a new game and select the PMHC01/Maul male portrait. Backup: '+str(mp)
  print(message)
  if interactive:messagebox.showinfo('Shadow Lord Rising',message)
  return 0
 except Exception as e:
  message=str(e);print('INSTALLATION STOPPED:',message,file=sys.stderr)
  if interactive:messagebox.showerror('Installation stopped',message)
  return 1
if __name__=='__main__':sys.exit(main())
