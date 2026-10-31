(()=>{'use strict';
const $=(s,p=document)=>p.querySelector(s),all=(s,p=document)=>Array.from(p.querySelectorAll(s));
$('#year').textContent=new Date().getFullYear();
const menu=$('#menu-button'),nav=$('#primary-nav');
menu.addEventListener('click',()=>{const open=nav.classList.toggle('open');menu.setAttribute('aria-expanded',String(open))});
all('.nav-links a').forEach(a=>a.addEventListener('click',()=>{nav.classList.remove('open');menu.setAttribute('aria-expanded','false')}));

// The review carousel supports arrows, interactive dots, touch swipes, and keyboard scrolling.
const reviewTabs=all('[data-review-tab]');
const reviewTracks=all('[data-review-track]');
const reviewDots=$('.review-dots');
const reviewCount=$('[data-review-count]');
let activeReviewKind='course';
function currentReviewTrack(){return reviewTracks.find(t=>t.dataset.reviewTrack===activeReviewKind)}
function carouselData(track){
  const cards=all('.review-card',track);
  const step=cards.length>1?cards[1].offsetLeft-cards[0].offsetLeft:(cards[0]?.offsetWidth||1);
  const maxIndex=Math.max(0,Math.ceil((track.scrollWidth-track.clientWidth-2)/Math.max(step,1)));
  const index=Math.min(maxIndex,Math.max(0,Math.round(track.scrollLeft/Math.max(step,1))));
  return {step,maxIndex,index};
}
function moveReviews(to){const track=currentReviewTrack(),{step,maxIndex}=carouselData(track);let index=to;if(index>maxIndex)index=0;if(index<0)index=maxIndex;track.scrollTo({left:Math.min(index*step,track.scrollWidth-track.clientWidth),behavior:'smooth'});setTimeout(updateCarouselUI,200)}
function updateCarouselUI(){
  const track=currentReviewTrack();if(!track)return;
  const {index,maxIndex}=carouselData(track);
  reviewCount.textContent=String(index+1).padStart(2,'0')+' / '+String(maxIndex+1).padStart(2,'0');
  if(reviewDots.children.length!==maxIndex+1){reviewDots.replaceChildren();for(let i=0;i<=maxIndex;i++){const dot=document.createElement('button');dot.type='button';dot.className='review-dot';dot.setAttribute('aria-label','Перейти до відгуку '+(i+1));dot.addEventListener('click',()=>moveReviews(i));reviewDots.appendChild(dot)}}
  all('.review-dot',reviewDots).forEach((dot,i)=>{dot.classList.toggle('active',i===index);dot.setAttribute('aria-current',i===index?'true':'false')});
}
reviewTabs.forEach(tab=>tab.addEventListener('click',()=>{
  activeReviewKind=tab.dataset.reviewTab;
  reviewTabs.forEach(el=>{const active=el===tab;el.classList.toggle('active',active);el.setAttribute('aria-pressed',String(active))});
  reviewTracks.forEach(track=>{track.hidden=track.dataset.reviewTrack!==activeReviewKind});
  currentReviewTrack().scrollLeft=0;
  updateCarouselUI();
}));
$('[data-review-prev]').addEventListener('click',()=>moveReviews(carouselData(currentReviewTrack()).index-1));
$('[data-review-next]').addEventListener('click',()=>moveReviews(carouselData(currentReviewTrack()).index+1));
reviewTracks.forEach(track=>track.addEventListener('scroll',()=>{if(track===currentReviewTrack())requestAnimationFrame(updateCarouselUI)},{passive:true}));
window.addEventListener('resize',updateCarouselUI);
updateCarouselUI();

// Gallery of five customer-chat screenshots, integrated with the reviews section.
const chatCards=all('[data-chat-open]'),chatTrack=$('[data-chat-track]'),chatCount=$('[data-chat-count]');
const chatDialog=$('#chat-proof-dialog'),modalImage=$('[data-chat-modal-image]'),modalCount=$('[data-chat-modal-count]');
let chatModalIndex=0;
function chatGeometry(){
  const step=chatCards.length>1?chatCards[1].offsetLeft-chatCards[0].offsetLeft:(chatCards[0]?.offsetWidth||1);
  const maxScroll=Math.max(0,chatTrack.scrollWidth-chatTrack.clientWidth);
  const maxIndex=Math.max(0,Math.ceil(maxScroll/Math.max(1,step)));
  const index=Math.max(0,Math.min(maxIndex,Math.round(chatTrack.scrollLeft/Math.max(1,step))));
  return {step,index,maxIndex,maxScroll};
}
function updateChatCounter(){const {index}=chatGeometry();chatCount.textContent=String(index+1).padStart(2,'0')+' / 05'}
function moveChats(direction){const {index,step,maxScroll}=chatGeometry();const target=(index+direction+chatCards.length)%chatCards.length;chatTrack.scrollTo({left:Math.min(target*step,maxScroll),behavior:'smooth'});setTimeout(updateChatCounter,300)}
$('[data-chat-prev]').addEventListener('click',()=>moveChats(-1));
$('[data-chat-next]').addEventListener('click',()=>moveChats(1));
chatTrack.addEventListener('scroll',()=>requestAnimationFrame(updateChatCounter),{passive:true});
window.addEventListener('resize',updateChatCounter);
function setChatModal(index){
  chatModalIndex=(index+chatCards.length)%chatCards.length;
  const thumbnail=$('img',chatCards[chatModalIndex]);
  modalImage.src=thumbnail.src;modalImage.alt=thumbnail.alt.replace('Скриншот','Збільшений скриншот');
  modalCount.textContent=String(chatModalIndex+1).padStart(2,'0')+' / 05';
}
chatCards.forEach((card,i)=>card.addEventListener('click',()=>{setChatModal(i);chatDialog.showModal()}));
$('[data-chat-close]').addEventListener('click',()=>chatDialog.close());
$('[data-chat-modal-prev]').addEventListener('click',()=>setChatModal(chatModalIndex-1));
$('[data-chat-modal-next]').addEventListener('click',()=>setChatModal(chatModalIndex+1));
chatDialog.addEventListener('click',(e)=>{if(e.target===chatDialog)chatDialog.close()});
chatDialog.addEventListener('keydown',(e)=>{if(e.key==='ArrowLeft'){e.preventDefault();setChatModal(chatModalIndex-1)}else if(e.key==='ArrowRight'){e.preventDefault();setChatModal(chatModalIndex+1)}});
updateChatCounter();

const service=$('select[name=service]');
all('[data-service]').forEach(el=>el.addEventListener('click',()=>{service.value=el.dataset.service;$('#order').scrollIntoView({behavior:'smooth'});setTimeout(()=>service.focus({preventScroll:true}),450)}));
const deadline=$('#deadline'),now=new Date(),localToday=new Date(now.getTime()-now.getTimezoneOffset()*60000).toISOString().slice(0,10);
deadline.min=localToday;
const form=$('#order-form'),submit=$('#submit-btn'),notice=$('#form-message'),contact=$('input[name=contact]');
function updateContact(clear=false){
  const channel=$('input[name=messenger]:checked').value,telegram=channel==='Telegram';
  $('#contact-label').innerHTML=telegram?'Твій нік у Telegram <b>*</b>':'Твій номер для '+channel+' <b>*</b>';
  $('#contact-hint').textContent=telegram?'Вкажи @нікнейм, щоб ми могли написати тобі першими.':'Вкажи номер із кодом країни, наприклад +380 99 123 45 67.';
  contact.placeholder=telegram?'@username':'+380 99 123 45 67';
  contact.type=telegram?'text':'tel';contact.inputMode=telegram?'text':'tel';contact.autocomplete=telegram?'off':'tel';
  if(clear)contact.value='';
}
all('input[name=messenger]').forEach(el=>el.addEventListener('change',()=>updateContact(true)));
updateContact();
const show=(txt,kind)=>{notice.textContent=txt;notice.className='form-message '+kind;notice.hidden=false};
form.addEventListener('submit',async(e)=>{
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
  finally{submit.disabled=false;submit.innerHTML='НАДІСЛАТИ ЗАЯВКУ <span class="arrow">↗</span>'}
});
})();