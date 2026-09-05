/**
 * Pure WS binary decode (from page-hook). UMD for content/SW/Node.
 */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.CornerAILib = Object.assign(root.CornerAILib || {}, api);
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
function bytesToHex(u8, max=64){
  const n=Math.min(u8.length, max);
  let s="";
  for(let i=0;i<n;i++) s+=(u8[i]<16?"0":"")+u8[i].toString(16);
  return s+(u8.length>max?"…":"");
}
function tryDecodeUtf8(u8){
  try{return new TextDecoder("utf-8",{fatal:false}).decode(u8)}catch{return null}
}
function tryExtractJsonIsland(text){
  if(!text||typeof text!=="string")return null;
  const t=text.trim();
  if((t[0]==="{"&&t[t.length-1]==="}")||(t[0]==="["&&t[t.length-1]==="]"))return t;
  // Search for first balanced {…} or […] that looks like JSON
  const startObj=t.indexOf("{"), startArr=t.indexOf("[");
  let start=-1, open="{", close="}";
  if(startObj>=0&&(startArr<0||startObj<=startArr)){start=startObj}
  else if(startArr>=0){start=startArr;open="[";close="]"}
  if(start<0)return null;
  let depth=0, inStr=false, esc=false;
  for(let i=start;i<t.length;i++){
    const c=t[i];
    if(inStr){if(esc)esc=false;else if(c==="\\")esc=true;else if(c==='"')inStr=false;continue}
    if(c==='"'){inStr=true;continue}
    if(c===open)depth++;
    else if(c===close){depth--;if(depth===0)return t.slice(start,i+1)}
  }
  return null;
}
function tryLengthPrefixedJson(u8){
  // Common patterns: 4-byte BE/LE length + payload, or 2-byte length
  if(u8.length<6)return null;
  const tryLen=(len,offset)=>{
    if(len<=0||offset+len>u8.length||len>2e6)return null;
    const slice=u8.subarray(offset,offset+len);
    const txt=tryDecodeUtf8(slice);
    if(!txt)return null;
    const island=tryExtractJsonIsland(txt);
    if(island){try{JSON.parse(island);return island}catch{}}
    return null;
  };
  // Big-endian uint32
  const be=((u8[0]<<24)|(u8[1]<<16)|(u8[2]<<8)|u8[3])>>>0;
  let r=tryLen(be,4);if(r)return r;
  // Little-endian uint32
  const le=((u8[3]<<24)|(u8[2]<<16)|(u8[1]<<8)|u8[0])>>>0;
  r=tryLen(le,4);if(r)return r;
  // Big-endian uint16
  const be16=(u8[0]<<8)|u8[1];
  r=tryLen(be16,2);if(r)return r;
  // Little-endian uint16
  const le16=(u8[1]<<8)|u8[0];
  r=tryLen(le16,2);if(r)return r;
  return null;
}
function deserializeBinaryFrame(raw){
  // Returns {text, decodedType, meta} or null
  let u8=null;
  try{
    if(raw instanceof ArrayBuffer) u8=new Uint8Array(raw);
    else if(ArrayBuffer.isView(raw)) u8=new Uint8Array(raw.buffer,raw.byteOffset,raw.byteLength);
    else if(raw instanceof Blob) return null; // handled async by caller
    else return null;
  }catch{return null}
  if(!u8||u8.length===0)return null;

  const meta={byteLength:u8.length,hexHead:bytesToHex(u8,48)};

  // 1) Direct UTF-8 → full text / JSON island
  const utf=tryDecodeUtf8(u8);
  if(utf){
    const island=tryExtractJsonIsland(utf);
    if(island){
      try{JSON.parse(island);return {text:island,decodedType:"utf8-json",meta}}
      catch{}
    }
    // Accept plain text that still looks like telemetry (existing inspect filters)
    if(utf.length>=8&&/[{\["]|attack|corner|escante|fixture|stats|pressure|xg|odds/i.test(utf)){
      return {text:utf,decodedType:"utf8-text",meta};
    }
  }

  // 2) Length-prefixed JSON
  const prefixed=tryLengthPrefixedJson(u8);
  if(prefixed) return {text:prefixed,decodedType:"length-prefixed-json",meta};

  // 3) Diagnostic only (do not drop silently)
  return {text:null,decodedType:"binary-unknown",meta};
}
  return {
    bytesToHex: bytesToHex,
    tryDecodeUtf8: tryDecodeUtf8,
    tryExtractJsonIsland: tryExtractJsonIsland,
    tryLengthPrefixedJson: tryLengthPrefixedJson,
    deserializeBinaryFrame: deserializeBinaryFrame
  };
});
