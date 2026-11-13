// Private selections live only in this page and are cleared at every auth boundary.
export const privateState = new Map<string,string>();
export function clearPrivateState(){
 privateState.clear();
 if(typeof window!=='undefined'){
  for(const key of ['caspian-active-voyage-v1','caspian-jit-demo-run-v1']){
   try{window.localStorage.removeItem(key);}catch{/* Storage may be disabled. */}
  }
 }
}
