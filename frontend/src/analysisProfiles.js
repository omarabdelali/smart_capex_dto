import axios from 'axios';
export const analysisApi = axios.create({baseURL:`${window.location.protocol}//${window.location.hostname}:8000/api`,withCredentials:true});
let csrf='',loading=null;
export function loadProfiles(){
  if(!loading)loading=analysisApi.get('/analysis/profiles/').then(({data})=>{csrf=data.csrf_token;return data;}).finally(()=>{loading=null;});
  return loading;
}
analysisApi.interceptors.request.use(async config=>{
  if(!csrf && config.url!=='/analysis/profiles/')await loadProfiles();
  return config;
});
export async function writeProfile(path,body,method='post'){
  if(!csrf)await loadProfiles();
  const {data}=await analysisApi.request({url:path,method,data:body,headers:{'X-CSRFToken':csrf}});
  window.dispatchEvent(new Event('analysis-profiles-updated'));
  return data;
}
