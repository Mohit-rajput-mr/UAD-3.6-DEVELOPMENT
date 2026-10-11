/* Draw a case's map with the Location Map tool in this browser, and save it
   into the report (T-416).

   The server draws the map itself where it has a browser of its own
   (app/mapper.py, the desktop edition and a local server).  The live site is
   a serverless function with none, so POST /maps answers state "browser" and
   the same tool runs here instead: out of sight, at the report's frame,
   seeded from the case, and it saves its PNG through /maps/image -- the
   request its own Save to report makes.  The tool's tiles and address
   look-ups are fetched by this browser, never by the server.

   UADDrawMap(caseId, {aerial}) resolves {ok:true, media_id} or
   {ok:false, error} -- the error in words, never "unknown error". */
(function(){
  'use strict';
  window.UADDrawMap = function(caseId, opts){
    opts = opts || {};
    return new Promise(function(resolve){
      var f = document.createElement('iframe'), timer = null;
      f.title = 'Drawing the map';
      f.setAttribute('aria-hidden', 'true');
      f.tabIndex = -1;
      /* laid out and painted (the tiles and the WebGL map need both), never seen or hit */
      f.style.cssText = 'position:fixed;left:0;top:0;width:900px;height:900px;border:0;'
        + 'opacity:0;pointer-events:none';
      function done(out){
        clearTimeout(timer);
        window.removeEventListener('message', heard);
        f.remove();
        resolve(out);
      }
      function heard(e){
        if (e.source === f.contentWindow && e.data && e.data.uad === 'map-drawn') done(e.data);
      }
      window.addEventListener('message', heard);
      timer = setTimeout(function(){
        done({ok:false, error:'the map tool did not finish within ' + Math.round((opts.timeout || 150000) / 1000) + ' seconds'});
      }, opts.timeout || 150000);
      f.src = '/ui/map/index.html?case=' + encodeURIComponent(caseId) + '&render=1&seed=1&post=1'
        + (opts.aerial ? '&aerial=1' : '');
      document.body.appendChild(f);
    });
  };
})();
