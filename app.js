(()=>{'use strict';
const $=(s,p=document)=>p.querySelector(s),all=(s,p=document)=>Array.from(p.querySelectorAll(s));
const year=$('#year'); if(year) year.textContent=new Date().getFullYear();
const menu=$('#menu-button'),nav=$('#primary-nav');
if(menu&&nav){
  menu.addEventListener('click',()=>{const open=nav.classList.toggle('open');menu.setAttribute('aria-expanded',String(open))});
  all('.nav-links a').forEach(a=>a.addEventListener('click',()=>{nav.classList.remove('open');menu.setAttribute('aria-expanded','false')}));
}

// Swipeable / clickable gallery of customer chat screenshots.
const chatCards=all('[data-chat-open]'),chatTrack=$('[data-chat-track]'),chatCount=$('[data-chat-count]');
const chatPrev=$('[data-chat-prev]'),chatNext=$('[data-chat-next]');
const chatDialog=$('#chat-proof-dialog'),modalImage=$('[data-chat-modal-image]'),modalCount=$('[data-chat-modal-count]');
const chatClose=$('[data-chat-close]'),modalPrev=$('[data-chat-modal-prev]'),modalNext=$('[data-chat-modal-next]');
let chatModalIndex=0;
function pad(n){return String(n).padStart(2,'0')}
if(chatCards.length && chatTrack){
  function chatGeometry(){
    const step=chatCards.length>1?chatCards[1].offsetLeft-chatCards[0].offsetLeft:(chatCards[0]?.offsetWidth||1);
    const maxScroll=Math.max(0,chatTrack.scrollWidth-chatTrack.clientWidth);
    const maxIndex=Math.max(0,Math.ceil(maxScroll/Math.max(1,step)));
    const index=Math.max(0,Math.min(maxIndex,Math.round(chatTrack.scrollLeft/Math.max(1,step))));
    return {step,index,maxIndex,maxScroll};
  }
  function updateChatCounter(){
    const {index}=chatGeometry();
    if(chatCount) chatCount.textContent=`${pad(index+1)} / 18`;
  }
  function moveChats(direction){
    const {index,step,maxScroll}=chatGeometry();
    const target=(index+direction+chatCards.length)%chatCards.length;
    chatTrack.scrollTo({left:Math.min(target*step,maxScroll),behavior:'smooth'});
    setTimeout(updateChatCounter,300);
  }
  if(chatPrev) chatPrev.addEventListener('click',()=>moveChats(-1));
  if(chatNext) chatNext.addEventListener('click',()=>moveChats(1));
  chatTrack.addEventListener('scroll',()=>requestAnimationFrame(updateChatCounter),{passive:true});
  window.addEventListener('resize',updateChatCounter);
  function setChatModal(index){
    chatModalIndex=(index+chatCards.length)%chatCards.length;
    const thumbnail=$('img',chatCards[chatModalIndex]);
    if(!thumbnail || !modalImage) return;
    modalImage.src=thumbnail.src;
    modalImage.alt=thumbnail.alt.replace('Скриншот','Збільшений скриншот');
    if(modalCount) modalCount.textContent=`${pad(chatModalIndex+1)} / 18`;
  }
  chatCards.forEach((card,i)=>card.addEventListener('click',()=>{ if(chatDialog){ setChatModal(i); chatDialog.showModal(); } }));
  if(chatClose&&chatDialog) chatClose.addEventListener('click',()=>chatDialog.close());
  if(modalPrev) modalPrev.addEventListener('click',()=>setChatModal(chatModalIndex-1));
  if(modalNext) modalNext.addEventListener('click',()=>setChatModal(chatModalIndex+1));
  if(chatDialog){
    chatDialog.addEventListener('click',(e)=>{if(e.target===chatDialog)chatDialog.close()});
    chatDialog.addEventListener('keydown',(e)=>{if(e.key==='ArrowLeft'){e.preventDefault();setChatModal(chatModalIndex-1)}else if(e.key==='ArrowRight'){e.preventDefault();setChatModal(chatModalIndex+1)}});
  }
  updateChatCounter();
}

const service=$('select[name=service]');
if(service) all('[data-service]').forEach(el=>el.addEventListener('click',()=>{service.value=el.dataset.service;$('#order').scrollIntoView({behavior:'smooth'});setTimeout(()=>service.focus({preventScroll:true}),450)}));
const deadline=$('#deadline'),now=new Date(),localToday=new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,10);
if(deadline) deadline.min=localToday;
const form=$('#order-form'),submit=$('#submit-btn'),notice=$('#form-message'),contact=$('input[name=contact]');
function updateContact(clear=false){
  const checked=$('input[name=messenger]:checked');
  if(!checked || !contact) return;
  const channel=checked.value,telegram=channel==='Telegram';
  $('#contact-label').innerHTML=telegram?'Твій нік у Telegram <b>*</b>':'Твій номер для '+channel+' <b>*</b>';
  $('#contact-hint').textContent=telegram?'Вкажи @нікнейм, щоб ми могли написати тобі першими.':'Вкажи номер із кодом країни, наприклад +380 99 123 45 67.';
  contact.placeholder=telegram?'@username':'+380 99 123 45 67';
  contact.type=telegram?'text':'tel';contact.inputMode=telegram?'text':'tel';contact.autocomplete=telegram?'off':'tel';
  if(clear)contact.value='';
}
all('input[name=messenger]').forEach(el=>el.addEventListener('change',()=>updateContact(true)));
updateContact();
const show=(txt,kind)=>{if(!notice) return; notice.textContent=txt;notice.className='form-message '+kind;notice.hidden=false};
if(form && submit && notice) form.addEventListener('submit',async(e)=>{
  e.preventDefault();notice.hidden=true;
  const data=Object.fromEntries(new FormData(form));
  if(!data.name?.trim()||!data.contact?.trim()||!data.service||!data.messenger){show('Заповни ім’я, обери месенджер і послугу, вкажи контакт .','error');return}
  data.contact=data.contact.trim();
  if(data.messenger==='Telegram'&&!/^@[A-Za-z0-9_]{5,32}$/.test(data.contact)){show('Для Telegram вкажи свій нік у форматі @username (від 5 символів після @).','error');contact.focus();return}
  if(data.messenger!=='Telegram'&&(!/^\+[\d\s()\-]+$/.test(data.contact)||data.contact.replace(/\D/g,'').length<8||data.contact.replace(/\D/g,'').length>15)){show('Для Viber або WhatsApp вкажи телефон із кодом країни, наприклад +380 99 123 45 67.','error');contact.focus();return}
  if(data.deadline&&data.deadline<localToday){show('Обери актуальну дату дедлайну.','error');return}
  submit.disabled=true;submit.textContent='НАДСИЛАЄМО…';
  try{
    const res=await fetch('/api/orders',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    const answer=await res.json();if(!res.ok)throw Error(answer.error||'Сталася помилка. Спробуй ще раз.');
    form.reset();updateContact();
    show(`Дякуємо! Заявку №${answer.id} збережено. Ми напишемо тобі в ${data.messenger} за вказаним контактом.`, 'success');
    notice.scrollIntoView({behavior:'smooth',block:'nearest'});
  }catch(err){show(err.message||'Не вдалося відправити. Перевір з’єднання та спробуй ще раз.','error')}
  finally{submit.disabled=false;submit.innerHTML='НАДІСЛАТИ ЗАЯВКУ <span class="arrow"><svg class="ui-arrow" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M5 19 19 5M8 5h11v11"/></svg></span>'}
});
})();