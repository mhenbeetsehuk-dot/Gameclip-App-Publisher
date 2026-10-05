
import React, {useState,useEffect} from "react";
import {View,Text,Pressable,StyleSheet,Alert,ActivityIndicator,ScrollView,TextInput} from "react-native";
import * as DocumentPicker from "expo-document-picker";
import Publishing from "./Publishing";
import * as SecureStore from "expo-secure-store";
import * as Sharing from "expo-sharing";
import { File, Paths } from "expo-file-system";
import { fetch as expoFetch } from "expo/fetch";

const API=process.env.EXPO_PUBLIC_API_URL || "https://gameclip-publisher.onrender.com";

export default function App(){
  const [api,setApi]=useState(API);
  const [apiKey,setApiKey]=useState("");
  const [clips,setClips]=useState([]);
  const [video,setVideo]=useState(null);
  const [busy,setBusy]=useState(false);
  const [testingServer,setTestingServer]=useState(false);
  const [serverStatus,setServerStatus]=useState("");
  const [count,setCount]=useState(6);
  const [length,setLength]=useState(30);
  const [vertical,setVertical]=useState(true);
  const [tab,setTab]=useState("create");

  useEffect(()=>{SecureStore.getItemAsync('gameclip-settings').then(raw=>{if(raw){const v=JSON.parse(raw);setApi(typeof v.api==='string'&&v.api?v.api:API);setApiKey(typeof v.apiKey==='string'?v.apiKey:'');}}).catch(()=>{});},[]);
  async function saveSettings(){
    const serverUrl=api.trim().replace(/\/+$/,'');
    const accessKey=apiKey.trim();
    if(!/^https:\/\//i.test(serverUrl)){Alert.alert('Check server URL','Enter the complete HTTPS address for your backend.');return;}
    if(!accessKey){Alert.alert('Access key required','Enter the GAMECLIP_API_KEY configured on your backend.');return;}
    try {
      await SecureStore.setItemAsync('gameclip-settings',JSON.stringify({api:serverUrl,apiKey:accessKey}));
      setApi(serverUrl);setApiKey(accessKey);setServerStatus('Settings saved securely on this phone.');
      Alert.alert('Saved','Backend URL and access key saved securely on this phone.');
    }catch(e){Alert.alert('Could not save settings',String(e.message||e));}
  }

  async function testServer(){
    const serverUrl=api.trim().replace(/\/+$/,'');
    const accessKey=apiKey.trim();
    if(!/^https:\/\//i.test(serverUrl)){Alert.alert('Check server URL','Enter the complete HTTPS address for your backend.');return;}
    if(!accessKey){Alert.alert('Access key required','Enter the GAMECLIP_API_KEY configured on your backend.');return;}
    setTestingServer(true);setServerStatus('Testing backend…');
    try{
      const response=await expoFetch(serverUrl+'/api/social',{headers:{'X-API-Key':accessKey}});
      const raw=await response.text();
      let result;try{result=JSON.parse(raw)}catch{throw new Error(`The server returned an unexpected response (${response.status}).`)}
      if(!response.ok)throw new Error(typeof result.detail==='string'?result.detail:`Server returned ${response.status}.`);
      const tiktok=result.platforms?.find(x=>x.platform==='tiktok');
      const summary=result.durable_storage
        ? `Connected. Persistent storage is ready; scheduler ${result.scheduler_enabled?'is enabled':'is off'}.${tiktok?.configured?' TikTok credentials are configured.':tiktok?.reason?` ${tiktok.reason}`:''}`
        : 'Backend reached, but persistent storage is not enabled. Account connections and scheduled uploads will not work until it is configured.';
      setServerStatus(summary);Alert.alert('Backend test',summary);
    }catch(e){
      const message=String(e.message||e);
      setServerStatus('Could not reach the backend. Check that it is running and the URL and access key are correct.');
      Alert.alert('Backend test failed',message);
    }finally{setTestingServer(false);}
  }

  async function pickVideo(){
    try {
      const result = await DocumentPicker.getDocumentAsync({type:"video/*",copyToCacheDirectory:true,multiple:false});
      if (!result.canceled) setVideo(result.assets[0]);
    } catch(e) { Alert.alert("Could not select video", String(e.message || e)); }
  }

  async function saveClip(clip){
    try {
      const dest = new File(Paths.cache, Date.now()+"-"+clip.name);
      const file = await File.downloadFileAsync(api.replace(/\/$/, "")+clip.download_path,dest,{headers:{"X-API-Key":apiKey}});
      if (await Sharing.isAvailableAsync()) await Sharing.shareAsync(file.uri,{mimeType:"video/mp4"});
      else Alert.alert("Downloaded",file.uri);
    } catch(e) { Alert.alert("Could not download", String(e.message || e)); }
  }

  async function createClips(){
    if(!video){Alert.alert("Choose a video first");return}
    if(!apiKey.trim()){setTab("settings");Alert.alert("Set up your server","Enter the server URL and access key first.");return}
    setBusy(true);
    try{
      const file = new File(video.uri);
      if (!file.exists) {
        throw new Error("The selected video cannot be read by the app. Please grant Photos/Videos permission and try again.");
      }
      const f=new FormData();
      f.append("video", file, video.name || "gameplay.mp4");
      f.append("clip_count",String(count));
      f.append("clip_duration",String(length));
      f.append("vertical",String(vertical));
      const r=await expoFetch(api.replace(/\/$/, "")+"/api/create-clips",{method:"POST",body:f,headers:{"X-API-Key":apiKey}});
      const raw=await r.text();
      let j; try {j=JSON.parse(raw)} catch {throw new Error(`Server returned ${r.status}. Check the server URL or try a shorter video.`)}
      if(!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : "Check your clip settings and try again.");
      setClips(j.clips || []);setTab("clips");
      Alert.alert("Clips ready",`${(j.clips||[]).length} clips created. ${j.message||""}`);
    }catch(e){Alert.alert("Could not create clips",String(e.message||e))}
    finally{setBusy(false)}
  }

  return (
    <View style={s.bg}>
      <ScrollView contentContainerStyle={s.body}>
        <Text style={s.title}>GAMECLIP PUBLISHER</Text>
        <Text style={s.sub}>Create • Download • Share</Text>

        <View style={s.tabs}>
          {["create","clips","queue","accounts","settings"].map(x=>(
            <Pressable key={x} onPress={()=>setTab(x)} style={[s.tab,tab===x&&s.tabOn]}>
              <Text style={s.white}>{x.toUpperCase()}</Text>
            </Pressable>
          ))}
        </View>

        {tab==="create" && <>
          <Text style={s.h}>Create clips</Text>
          <Pressable style={s.pick} onPress={pickVideo}>
            <Text style={s.white}>{video?.name || "📁 Choose gameplay video"}</Text>
          </Pressable>

          <Text style={s.label}>NUMBER OF CLIPS</Text>
          <View style={s.row}>{[3,6,10,15].map(n=>
            <Pressable key={n} onPress={()=>setCount(n)} style={[s.chip,count===n&&s.active]}>
              <Text style={s.white}>{n}</Text>
            </Pressable>)}</View>

          <Text style={s.label}>CLIP LENGTH</Text>
          <View style={s.row}>{[15,30,45,60].map(n=>
            <Pressable key={n} onPress={()=>setLength(n)} style={[s.chip,length===n&&s.active]}>
              <Text style={s.white}>{n}s</Text>
            </Pressable>)}</View>

          <Pressable style={s.option} onPress={()=>setVertical(!vertical)}>
            <Text style={s.white}>{vertical ? "📱 9:16 Vertical" : "🖥 Landscape"}</Text>
          </Pressable>

          <Text style={s.note}>
            The server chooses sections using visual motion and creates clips. Use a video under 200 MB and 30 minutes. Short videos may produce fewer clips.
          </Text>

          {busy ? <ActivityIndicator color="#fff" style={{marginTop:28}}/> :
            <Pressable style={s.primary} onPress={createClips}>
              <Text style={s.white}>CREATE CLIPS</Text>
            </Pressable>}
        </>}

        {tab==="clips" && <>
          <Text style={s.h}>Your clips</Text>
          <Text style={s.sub}>Clips are temporary. Download them before the server restarts.</Text>
          {clips.length===0 && <Text style={s.note}>Create clips to see them here.</Text>}
          {clips.map(clip=><Pressable key={clip.download_path} style={s.card} onPress={()=>saveClip(clip)}><Text style={s.white}>{clip.name}</Text><Text style={s.small}>Download / Share</Text></Pressable>)}
        </>}

        {(tab==="queue"||tab==="accounts") && <Publishing api={api} apiKey={apiKey} mode={tab}/> }
        {tab==="settings" && <>
          <Text style={s.h}>Server settings</Text>
          <Text style={s.note}>Enter the HTTPS address of the computer or service running GameClip Publisher and its access key. These values are saved securely on this phone.</Text>
          <Text style={s.label}>SERVER URL</Text>
          <TextInput style={[s.card,{color:"white"}]} value={api} onChangeText={value=>{setApi(value);setServerStatus('');}} autoCapitalize="none" autoCorrect={false} keyboardType="url" placeholder="https://your-server.example.com" placeholderTextColor="#8792a0" accessibilityLabel="Server URL"/>
          <Text style={s.label}>ACCESS KEY</Text>
          <TextInput style={[s.card,{color:"white"}]} value={apiKey} onChangeText={value=>{setApiKey(value);setServerStatus('');}} secureTextEntry autoCapitalize="none" autoCorrect={false} placeholder="GAMECLIP_API_KEY from your server" placeholderTextColor="#8792a0" accessibilityLabel="Server access key"/>
          <View style={s.settingsActions}>
            <Pressable style={[s.primary,s.settingsAction]} disabled={testingServer} onPress={testServer}><Text style={s.white}>{testingServer?'Testing…':'Test connection'}</Text></Pressable>
            <Pressable style={[s.primary,s.settingsAction]} onPress={saveSettings}><Text style={s.white}>Save settings</Text></Pressable>
          </View>
          {!!serverStatus&&<Text style={s.status}>{serverStatus}</Text>}
          <Text style={s.note}>TikTok, YouTube, and Meta developer secrets belong on the backend; don’t enter them in the APK. Connect social accounts from the Accounts tab after the backend test succeeds.</Text>
        </>}
      </ScrollView>
    </View>
  );
}

const s=StyleSheet.create({
  bg:{flex:1,backgroundColor:"#0b0f14"},
  body:{padding:22,paddingTop:70,paddingBottom:50},
  title:{color:"#fff",fontSize:27,fontWeight:"900"},
  sub:{color:"#8c97a5",marginTop:6,lineHeight:21},
  tabs:{flexDirection:"row",flexWrap:"wrap",gap:8,marginTop:25,marginBottom:25},
  settingsActions:{flexDirection:"row",gap:10,flexWrap:"wrap"},
  settingsAction:{flexGrow:1},
  tab:{backgroundColor:"#171e27",paddingVertical:10,paddingHorizontal:14,borderRadius:18},
  tabOn:{backgroundColor:"#2f81f7"},
  h:{color:"#fff",fontSize:28,fontWeight:"800",marginBottom:18},
  pick:{backgroundColor:"#151b23",borderRadius:14,padding:20},
  label:{color:"#8792a0",fontSize:12,fontWeight:"700",marginTop:20,marginBottom:8},
  row:{flexDirection:"row",gap:8,flexWrap:"wrap"},
  chip:{backgroundColor:"#171e27",padding:12,borderRadius:20},
  active:{backgroundColor:"#2f81f7"},
  option:{backgroundColor:"#171e27",padding:15,borderRadius:12,marginTop:20},
  note:{color:"#7e8996",lineHeight:20,marginTop:20},
  primary:{backgroundColor:"#2f81f7",padding:17,borderRadius:13,alignItems:"center",marginTop:25},
  white:{color:"#fff",fontWeight:"700"},
  card:{backgroundColor:"#151b23",padding:18,borderRadius:14,marginTop:15},
  status:{color:"#b8d7ff",lineHeight:21,marginTop:16},
  big:{color:"#fff",fontSize:26,fontWeight:"800",marginTop:6},
  small:{color:"#808b99",marginTop:5}
});
