/* Nexa Business Hub - Writing Assistant
 * Free template-based drafts and local text cleanup.
 * This file does not claim to provide AI translation or AI grammar correction.
 */
(function(){
 "use strict";
 const el=id=>document.getElementById(id);
 const msg=(text,type="info")=>{const node=el("waMessage");if(!node)return;node.textContent=text;node.className="message show "+type;};
 const val=id=>(el(id)?.value||"").trim();
 window.nexaGenerateWriting=function(){
  const lang=val("waLanguage")||"ur", type=val("waType")||"general";
  const recipient=val("waRecipient"), name=val("waName")|| (lang==="ur"?"درخواست گزار":"Applicant");
  const reason=val("waReason"), details=val("waDetails");
  if(!reason){msg(lang==="ur"?"Meherbani karke subject ya reason likhein.":"Please enter a subject or reason.","error");el("waReason")?.focus();return;}
  let result="";
  if(lang==="ur"){
   const to=recipient||"جنابِ محترم";
   const opening=type==="leave"?"مؤدبانہ گزارش ہے کہ مجھے "+reason+" کی وجہ سے رخصت درکار ہے۔":
    type==="job"?"مؤدبانہ گزارش ہے کہ میں "+reason+" کے لیے درخواست دینا چاہتا/چاہتی ہوں۔":
    type==="admission"?"مؤدبانہ گزارش ہے کہ میں "+reason+" کے لیے داخلے کی درخواست پیش کرتا/کرتی ہوں۔":
    "مؤدبانہ گزارش ہے کہ "+reason+" کے سلسلے میں میری درخواست پر غور فرمایا جائے۔";
   result=to+"\n\nموضوع: "+reason+"\n\nجنابِ عالی!\n"+opening+(details?"\n\nمزید تفصیل: "+details:"")+"\n\nبراہِ کرم میری درخواست پر ہمدردانہ غور فرمائیں۔ آپ کی مہربانی ہوگی۔\n\nخاکسار،\n"+name+"\nتاریخ: __________";
  }else{
   const to=recipient||"The Concerned Officer";
   const opening=type==="leave"?"I respectfully request leave due to "+reason+".":
    type==="job"?"I am writing to apply for "+reason+". I would appreciate your consideration of my application.":
    type==="admission"?"I would like to apply for admission regarding "+reason+". Kindly consider my request.":
    "I respectfully request your consideration regarding "+reason+".";
   result="To,\n"+to+"\n\nSubject: "+reason+"\n\nDear Sir/Madam,\n"+opening+(details?"\n\nAdditional details: "+details:"")+"\n\nThank you for your time and consideration.\n\nSincerely,\n"+name+"\nDate: __________";
  }
  el("waOutput").value=result;msg("Draft ready. Please review all details before using it.","success");
 };
 window.nexaCopyWriting=async function(){
  const output=el("waOutput");if(!output||!output.value.trim()){msg("Pehle draft generate karein ya output box mein text likhein.","error");return;}
  try{await navigator.clipboard.writeText(output.value);msg("Text copied.","success");}
  catch(e){output.focus();output.select();try{const ok=document.execCommand("copy");msg(ok?"Text copied.":"Copy automatic nahi hua; text select karke copy karein.",ok?"success":"error");}catch(err){msg("Text select karke manually copy karein.","error");}}
 };
 window.nexaDownloadWriting=function(){
  const text=val("waOutput");if(!text){msg("Pehle draft generate karein ya output box mein text likhein.","error");return;}
  const blob=new Blob(["\uFEFF"+text],{type:"text/plain;charset=utf-8"}),url=URL.createObjectURL(blob),a=document.createElement("a");
  a.href=url;a.download="nexa-writing-draft.txt";document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);msg("TXT download start ho gaya.","success");
 };
 window.nexaCleanWriting=function(){
  const input=el("waBasicText");if(!input||!input.value.trim()){msg("Cleanup ke liye pehle text paste karein.","error");return;}
  const cleaned=input.value.replace(/[\\t ]+/g," ").replace(/ *\\n */g,"\n").replace(/\\n{3,}/g,"\n\n").trim();
  el("waOutput").value=cleaned;msg("Extra spaces clean kar di gayi hain. Ye basic cleanup hai, AI grammar correction nahi.","success");
 };
 window.nexaClearWriting=function(){["waRecipient","waName","waReason","waDetails","waOutput","waBasicText"].forEach(id=>{if(el(id))el(id).value="";});msg("Fields clear ho gaye.","info");};
})();