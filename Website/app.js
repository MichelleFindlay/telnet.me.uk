var HOSTS = [
  { host:"roulette.c.telnet.me.uk", port:21596,   desc:"The Roulette Wheel" },
];

var result=document.getElementById("result");
function rnd(a,b){ return Math.floor(Math.random()*(b-a+1))+a; }
function esc(s){ return s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

function pull(){
  var btn=document.getElementById("btn");
  var ticket=document.getElementById("ticket");
  btn.disabled=true;
  ticket.textContent="SPINNING...";
  result.innerHTML='<div class="machine"><div class="wheel"></div><div class="label">Spinning the wheel&hellip;</div></div>';

  setTimeout(function(){
    var t=HOSTS[rnd(0,HOSTS.length-1)];
    var cmd="telnet "+t.host+" "+t.port;
    ticket.textContent="TICKET #"+String(rnd(1,999999)).padStart(6,"0");
    result.innerHTML=
      '<div class="reveal">'+
      '<div class="host">&gt; '+esc(t.host)+' :'+t.port+'</div>'+
      '<div class="desc">'+esc(t.desc)+'</div>'+
      '<div class="cmd"><code id="cmd">'+esc(cmd)+'</code>'+
      '<button class="copy" type="button">COPY</button></div>'+
      '<div class="note">Paste this into your terminal to connect. '+
      'To quit telnet, press <b>Ctrl+C</b> then type <b>quit</b>. '+
      'No telnet? Try <code>nc '+esc(t.host)+' '+t.port+'</code> instead.</div>'+
      '</div>';
    btn.disabled=false;
  },1200);
}

function hexDim(hex){
  var n=parseInt(hex.slice(1),16);
  var r=Math.round(((n>>16)&255)*0.55), g=Math.round(((n>>8)&255)*0.55), b=Math.round((n&255)*0.55);
  return '#'+[r,g,b].map(function(v){ return v.toString(16).padStart(2,"0"); }).join("");
}
function hexBg(hex){
  var n=parseInt(hex.slice(1),16);
  var r=Math.round(((n>>16)&255)*0.06)+4, g=Math.round(((n>>8)&255)*0.06)+5, b=Math.round((n&255)*0.06)+4;
  return '#'+[r,g,b].map(function(v){ return Math.min(v,255).toString(16).padStart(2,"0"); }).join("");
}
function setTheme(fg,dim,bg){
  document.documentElement.style.setProperty("--fg",fg);
  document.documentElement.style.setProperty("--dim",dim);
  document.documentElement.style.setProperty("--bg",bg);
  try{
    localStorage.setItem("rouletteFg",fg);
    localStorage.setItem("rouletteDim",dim);
    localStorage.setItem("rouletteBg",bg);
  }catch(e){}
}
document.getElementById("btn").addEventListener("click",pull);
result.addEventListener("click",function(e){
  if(e.target.classList.contains("copy")) copyCmd();
});
document.querySelectorAll(".swatch").forEach(function(s){
  s.style.setProperty("--sw",s.dataset.fg);
  s.addEventListener("click",function(){
    setTheme(s.dataset.fg,s.dataset.dim,s.dataset.bg);
    document.querySelectorAll(".swatch").forEach(function(x){ x.classList.remove("active"); });
    s.classList.add("active");
    document.getElementById("customColor").value=s.dataset.fg;
  });
});
document.getElementById("customColor").addEventListener("input",function(e){
  setTheme(e.target.value,hexDim(e.target.value),hexBg(e.target.value));
  document.querySelectorAll(".swatch").forEach(function(x){ x.classList.remove("active"); });
});
(function(){
  try{
    var fg=localStorage.getItem("rouletteFg"), dim=localStorage.getItem("rouletteDim"),
        bg=localStorage.getItem("rouletteBg");
    if(fg&&dim&&bg){
      setTheme(fg,dim,bg);
      document.getElementById("customColor").value=fg;
      var match=document.querySelector('.swatch[data-fg="'+fg+'"]');
      document.querySelectorAll(".swatch").forEach(function(x){ x.classList.remove("active"); });
      if(match) match.classList.add("active");
    }
  }catch(e){}
})();

(function(){
  var rain=document.getElementById("rain");
  var chars=["🎰","♠","♥","♦","♣","🎲","7","0","$","●"];
  var n=Math.ceil(window.innerWidth/28);
  var cols=[];

  for(var i=0;i<n;i++){
    var col=document.createElement("div");
    col.className="rain-col";
    var baseX=i*28;
    col.style.left=baseX+"px";
    var len=18+Math.floor(Math.random()*12);
    var text="";
    for(var j=0;j<len;j++){ text+=chars[Math.floor(Math.random()*chars.length)]+"\n"; }
    col.textContent=text;
    rain.appendChild(col);
    cols.push({ el:col, y:-Math.random()*window.innerHeight*1.6, speed:18+Math.random()*22 });
  }

  var lastTime=null;
  function frame(t){
    if(lastTime===null) lastTime=t;
    var dt=Math.min((t-lastTime)/1000,0.05);
    lastTime=t;
    var vh=window.innerHeight;

    for(var k=0;k<cols.length;k++){
      var c=cols[k];
      c.y+=c.speed*dt;
      if(c.y>vh+40) c.y=-40-Math.random()*200;
      c.el.style.transform="translateY("+c.y.toFixed(1)+"px)";
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
})();

(function(){
  var rain=document.getElementById("rain");
  var bgToggle=document.getElementById("bgToggle");
  function applyBg(on){
    rain.style.display=on?"":"none";
    bgToggle.textContent="BG: "+(on?"ON":"OFF");
    bgToggle.classList.toggle("off",!on);
  }
  bgToggle.addEventListener("click",function(){
    applyBg(rain.style.display==="none");
    try{ localStorage.setItem("rouletteBgOn",rain.style.display==="none"?"0":"1"); }catch(e){}
  });
  try{
    if(localStorage.getItem("rouletteBgOn")==="0") applyBg(false);
  }catch(e){}
})();

function copyCmd(){
  var txt=document.getElementById("cmd").textContent;
  navigator.clipboard.writeText(txt).then(function(){
    var b=document.querySelector(".copy"); var o=b.textContent;
    b.textContent="COPIED"; setTimeout(function(){ b.textContent=o; },1200);
  });
}
