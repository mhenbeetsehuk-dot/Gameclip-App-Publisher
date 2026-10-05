import React,{useState,useEffect} from 'react';
import {View,Text,Pressable,TextInput,Alert,Linking,AppState} from 'react-native';

export default function Publishing({api,apiKey,mode}){
  const [social,setSocial]=useState({platforms:[]});
  const [library,setLibrary]=useState([]);
  const [jobs,setJobs]=useState([]);
  const [selected,setSelected]=useState([]);
  const [platforms,setPlatforms]=useState([]);
  const [title,setTitle]=useState('');
  const [caption,setCaption]=useState('');
  const [when,setWhen]=useState(new Date(Date.now()+3600000).toISOString());
  const [interval,setInterval]=useState('3');
  const [madeForKids,setMadeForKids]=useState(false);
  const [privacy,setPrivacy]=useState('private');
  const [busy,setBusy]=useState(false);
  async function request(path,method='GET',body){
    if(!apiKey) throw new Error('Enter your access key in Settings.');
    const r=await fetch(api.replace(/\/$/,'')+path,{method,headers:{'X-API-Key':apiKey,'Content-Type':'application/json'},body:body?JSON.stringify(body):undefined});
    let j;try{j=await r.json()}catch{throw new Error('Server unavailable. Check Settings and try again.');}
    if(!r.ok)throw new Error(typeof j.detail==='string'?j.detail:'Check your selections and schedule time.');
    return j;
  }
  async function refresh(){
    try{
      const [s,l,q]=await Promise.all([request('/api/social'),request('/api/library'),request('/api/queue')]);
      setSocial(s);setLibrary(l);setJobs(q);
    }catch(e){Alert.alert('Could not load publishing',e.message);}
  }
  useEffect(()=>{if(apiKey)refresh();const sub=AppState.addEventListener('change',x=>{if(x==='active'&&apiKey)refresh();});return()=>sub.remove();},[api,apiKey]);
  async function action(fn){setBusy(true);try{await fn();await refresh();}catch(e){Alert.alert('Could not complete action',e.message);}finally{setBusy(false);}}
  function toggle(list,setter,id){setter(list.includes(id)?list.filter(x=>x!==id):[...list,id]);}
  async function connect(p){await action(async()=>{const j=await request(`/api/social/${p}/connect`,'POST');await Linking.openURL(j.url);});}
  async function choose(p){await action(async()=>{
    const choices=await request(`/api/social/${p}/choices`);
    if(!choices.length)throw new Error('No eligible accounts found. Check your Page and professional account permissions.');
    Alert.alert('Select account','Choose the account you want to publish to.',choices.slice(0,10).map(c=>({text:c.instagram?.username||c.name,onPress:()=>action(()=>request(`/api/social/${p}/select`,'POST',{page_id:c.id}))})).concat([{text:'Cancel',style:'cancel'}]));
  });}
  function enqueue(){
    if(!selected.length||!platforms.length||!title.trim())return Alert.alert('Choose your posts','Select clips, platforms and enter a title.');
    if(Number.isNaN(Date.parse(when)))return Alert.alert('Invalid date','Use an ISO date with timezone, for example 2026-10-04T09:00:00+01:00.');
    Alert.alert('Approve scheduled uploads',`${selected.length} clips to ${platforms.join(', ')}. First upload: ${when}. Then every ${interval} hours. Title, caption and supported platform settings will be applied automatically when each item is due. YouTube visibility: ${privacy}. Made for kids: ${madeForKids?'yes':'no'}. TikTok sends a draft to your inbox; its API does not let this draft flow apply the caption or publish it, so finish those steps in TikTok.`,[
      {text:'Cancel',style:'cancel'},
      {text:'Schedule',onPress:()=>action(async()=>{await request('/api/queue','POST',{clip_ids:selected,platforms,title:title.trim(),caption,first_at:when,interval_hours:Number(interval),youtube_privacy:privacy,made_for_kids:madeForKids,consent:true});setSelected([]);Alert.alert('Scheduled','Your server will handle the uploads.');})}
    ]);
  }
  const Button=({text,onPress})=><Pressable disabled={busy} style={s.button} onPress={onPress}><Text style={s.white}>{text}</Text></Pressable>;
  return <View>
    <Button text={busy?'Working…':'Refresh'} onPress={refresh}/>
    {mode==='accounts'?<>
      <Text style={s.heading}>Social accounts</Text>
      {!social.durable_storage&&<Text style={s.note}>Scheduling needs persistent storage and an always-on server. Your current free server cannot guarantee scheduled uploads.</Text>}
      {social.platforms.map(p=><View key={p.platform} style={s.card}>
        <Text style={s.white}>{p.platform.toUpperCase()} · {p.connected?'Connected':'Disconnected'}</Text>
        <Text style={s.note}>{p.label||p.reason||'Ready to connect'}{ '\n'}{p.mode}</Text>
        <Button text={p.connected?'Reconnect':'Connect'} onPress={()=>connect(p.platform)}/>
        {p.connected&&['facebook','instagram'].includes(p.platform)&&<Button text="Select account" onPress={()=>choose(p.platform)}/>}
        {p.connected&&<Button text="Disconnect" onPress={()=>Alert.alert('Disconnect account','Cancel its queued uploads and remove saved credentials?', [{text:'Cancel'},{text:'Disconnect',onPress:()=>action(()=>request(`/api/social/${p.platform}`,'DELETE'))}])}/>}
      </View>)}
    </>:<>
      <Text style={s.heading}>Schedule clips</Text>
      <Text style={s.note}>Choose saved clips and connected accounts. Times must include a timezone. Titles, captions and supported settings are applied automatically when scheduled uploads run. TikTok draft uploads still need you to finish the caption and publish in TikTok.</Text>
      {library.map(c=><Button key={c.id} text={(selected.includes(c.id)?'✓ ':'')+c.name} onPress={()=>toggle(selected,setSelected,c.id)}/>)}
      {!library.length&&<Text style={s.note}>No saved clips. Persistent storage must be enabled before creating clips for scheduling.</Text>}
      {social.platforms.filter(p=>p.connected).map(p=><Button key={p.platform} text={(platforms.includes(p.platform)?'✓ ':'')+p.platform} onPress={()=>toggle(platforms,setPlatforms,p.platform)}/>)}
      <TextInput style={s.input} placeholder="Title" placeholderTextColor="#8792a0" value={title} onChangeText={setTitle} maxLength={100}/>
      <TextInput style={s.input} placeholder="Caption / description" placeholderTextColor="#8792a0" value={caption} onChangeText={setCaption} multiline maxLength={2200}/>
      <Text style={s.note}>First upload (ISO date with timezone)</Text>
      <TextInput style={s.input} value={when} onChangeText={setWhen} autoCapitalize="none"/>
      <Text style={s.note}>Hours between clips</Text>
      <TextInput style={s.input} value={interval} onChangeText={setInterval} keyboardType="numeric"/>
      <Text style={s.note}>YouTube visibility</Text>
      {['private','unlisted','public'].map(p=><Button key={p} text={(privacy===p?'✓ ':'')+p} onPress={()=>setPrivacy(p)}/>)}
      <Button text={madeForKids?"Audience: Made for kids":"Audience: Not made for kids"} onPress={()=>setMadeForKids(!madeForKids)}/>
      <Button text="Review and schedule" onPress={enqueue}/>
      <Text style={s.heading}>Publishing queue</Text>
      {jobs.map(j=><View key={j.id} style={s.card}><Text style={s.white}>{j.name} → {j.platform}</Text><Text style={s.note}>{new Date(j.due*1000).toLocaleString()}{'\n'}{j.status}{j.error?'\n'+j.error:''}{j.status==='awaiting_user'?'\nOpen TikTok inbox to complete posting.':''}</Text>{j.status==='queued'&&<Button text="Cancel upload" onPress={()=>action(()=>request(`/api/queue/${j.id}`,'DELETE'))}/>}</View>)}
    </>}
  </View>;
}
const s={white:{color:'white',fontWeight:'700'},heading:{color:'white',fontSize:25,fontWeight:'800',marginTop:22},note:{color:'#a5afbd',lineHeight:21,marginTop:10},button:{backgroundColor:'#246bcc',padding:13,borderRadius:12,marginTop:10},card:{backgroundColor:'#151b23',padding:16,borderRadius:14,marginTop:16},input:{color:'white',backgroundColor:'#171e27',padding:14,borderRadius:10,marginTop:12}};
