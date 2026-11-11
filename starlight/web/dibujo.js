// El dibujo de la Starlight, compartido por el tablero y el editor.
// StarlightDibujo.dibujar(svg, { tocar(id) }) devuelve { piezas, franja, tocables(ids, etiqueta), marcar(clase, ids) }.
'use strict';
(function () {
  const NS = 'http://www.w3.org/2000/svg';

  // Nombre de cada control, como está impreso en el aparato
  const NOMBRES = { play: 'Play', cue: 'Cue', sync: 'Sync', pfl: 'PFL', 'jog.toque': 'Jog (tocar)', jog: 'Jog', volumen: 'Volume',
    eq: 'Bass', tempo: 'Tempo', 'modo.hotcue': 'Hot Cue', 'modo.loop': 'Loop', 'modo.fx': 'FX', 'modo.sampler': 'Sampler' };
  const GLOBALES = { shift: 'Shift', bassfilter: 'Bass/Filter', vinyl: 'Vinyl', crossfader: 'Crossfader', master: 'Master', audifonos: 'Headphones' };
  function nombreControl(c) {
    if (GLOBALES[c]) return GLOBALES[c];
    const [d, ...r] = c.split('.'); const x = r.join('.');
    return x.startsWith('pad') ? `Pad ${x.slice(3)} ${d}` : `${NOMBRES[x] || x} ${d}`;
  }

  function dibujar(svg, opciones = {}) {
    const piezas = {};
    const grupos = [];  // [id, g, nombre] de lo que se puede tocar
    function el(tag, attrs, padre) {
      const e = document.createElementNS(NS, tag);
      for (const [k, v] of Object.entries(attrs || {})) e.setAttribute(k, v);
      if (padre) padre.appendChild(e);
      return e;
    }
    function texto(x, y, s, clase, padre, anchor = 'middle') {
      const t = el('text', { x, y, class: clase, 'text-anchor': anchor }, padre);
      t.textContent = s;
      return t;
    }
    function interactivo(g, id) {
      grupos.push([id, g, nombreControl(id)]);
      const tocar = () => { if (g.classList.contains('tocable') && opciones.tocar) opciones.tocar(id); };
      g.addEventListener('click', tocar);
      g.addEventListener('keydown', e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); tocar(); } });
    }

    if (!svg.querySelector('#arcoiris')) {
      const defs = el('defs', {}, svg);
      const lg = el('linearGradient', { id: 'arcoiris', x1: 0, x2: 1 }, defs);
      [['0', '#ff3d3d'], ['.33', '#ffd23d'], ['.66', '#3dd6ff'], ['1', '#b03dff']].forEach(([o, c]) => el('stop', { offset: o, 'stop-color': c }, lg));
    }
    el('rect', { x: 12, y: 12, width: 1176, height: 320, rx: 40, class: 'placa' }, svg);
    const franja = {
      izq: el('rect', { x: 64, y: 348, width: 532, height: 10, rx: 5, class: 'base' }, svg),
      der: el('rect', { x: 604, y: 348, width: 532, height: 10, rx: 5, class: 'base' }, svg),
    };

    function boton(id, x, y, w, h, rotulo) {
      const g = el('g', { class: 'boton' }, svg);
      el('rect', { x, y, width: w, height: h, rx: 6 }, g);
      texto(x + w / 2, y + h / 2 + 4.5, rotulo, 'rotulo', g);
      piezas[id] = { g };
      if (id !== 'shift') interactivo(g, id);
    }
    function redondo(id, cx, cy, r, etiqueta) {
      const g = el('g', { class: 'boton' }, svg);
      el('circle', { cx, cy, r, class: 'boton-c' }, g);
      texto(cx, cy + r + 19, etiqueta, 'etq', svg);
      piezas[id] = { g };
      interactivo(g, id);
    }
    function perilla(id, cx, cy, r, etiqueta) {
      const g = el('g', { class: 'perilla' }, svg);
      el('circle', { cx, cy, r, class: 'cuerpo' }, g);
      const ind = el('line', { x1: cx, y1: cy - r + 5, x2: cx, y2: cy - r * 0.3, class: 'indicador' }, g);
      const t = texto(cx, cy + r + 19, etiqueta, 'etq', svg);
      piezas[id] = { g, etiqueta: t, poner: v => ind.setAttribute('transform', `rotate(${-135 + v * 270} ${cx} ${cy})`) };
      piezas[id].poner(0.5);
      interactivo(g, id);
    }
    function faderVertical(id, x, y1, y2, etiqueta) {
      const g = el('g', { class: 'fader' }, svg);
      el('rect', { x: x - 18, y: y1 - 10, width: 36, height: y2 - y1 + 20, fill: 'transparent' }, g);  // zona para el clic
      el('line', { x1: x, y1, x2: x, y2, class: 'riel' }, g);
      const tapa = el('g', {}, g);
      el('rect', { x: x - 15, y: -7, width: 30, height: 14, rx: 3, class: 'tapa' }, tapa);
      el('line', { x1: x - 9, y1: 0, x2: x + 9, y2: 0, class: 'tapa-linea' }, tapa);
      texto(x, y2 + 26, etiqueta, 'etq', svg);
      // verificado en el aparato (2026-11-10): el valor sube cuando el fader va hacia arriba
      piezas[id] = { g, poner: v => tapa.setAttribute('transform', `translate(0 ${y2 - v * (y2 - y1)})`) };
      piezas[id].poner(0.5);
      interactivo(g, id);
    }
    function faderHorizontal(id, x1, x2, y, etiqueta) {
      const g = el('g', { class: 'fader' }, svg);
      el('rect', { x: x1 - 10, y: y - 20, width: x2 - x1 + 20, height: 40, fill: 'transparent' }, g);
      el('line', { x1, y1: y, x2, y2: y, class: 'riel' }, g);
      const tapa = el('g', {}, g);
      el('rect', { x: -8, y: y - 17, width: 16, height: 34, rx: 3, class: 'tapa' }, tapa);
      el('line', { x1: 0, y1: y - 10, x2: 0, y2: y + 10, class: 'tapa-linea' }, tapa);
      texto((x1 + x2) / 2, y + 42, etiqueta, 'etq', svg);
      piezas[id] = { g, poner: v => tapa.setAttribute('transform', `translate(${x1 + v * (x2 - x1)} 0)`) };
      piezas[id].poner(0.5);
      interactivo(g, id);
    }
    function jog(deck, cx, cy) {
      const g = el('g', { class: 'jog' }, svg);
      el('circle', { cx, cy, r: 104, class: 'aro' }, g);
      el('circle', { cx, cy, r: 82, class: 'plato' }, g);
      const marca = el('g', {}, g);
      el('circle', { cx, cy: cy - 93, r: 5, class: 'marcador' }, marca);
      el('circle', { cx, cy, r: 4, class: 'centro' }, g);
      let angulo = 0;
      piezas[`${deck}.jog`] = { g, girar: pasos => { angulo = (angulo + pasos * 1.5) % 360; marca.setAttribute('transform', `rotate(${angulo} ${cx} ${cy})`); } };
      piezas[`${deck}.jog.toque`] = { g };
      interactivo(g, `${deck}.jog`);
    }
    function pads(deck, x0, y0) {
      for (let i = 1; i <= 4; i++) {
        const x = x0 + ((i - 1) % 2) * 64, y = y0 + Math.floor((i - 1) / 2) * 64;
        const g = el('g', { class: 'pad' }, svg);
        el('rect', { x, y, width: 56, height: 56, rx: 8 }, g);
        texto(x + 9, y + 19, String(i), 'num', g, 'start');
        piezas[`${deck}.pad${i}`] = { g };
        interactivo(g, `${deck}.pad${i}`);
      }
    }
    function modos(deck, x0, y) {
      const pares = [['hotcue', 'fx', 'Hot Cue', 'FX'], ['loop', 'sampler', 'Loop', 'Sampler']];
      pares.forEach(([principal, secundario, r1, r2], k) => {
        const x = x0 + k * 63;
        const g = el('g', { class: 'boton' }, svg);
        el('rect', { x, y, width: 57, height: 24, rx: 6 }, g);
        const t = texto(x + 28.5, y + 16.5, r1, 'rotulo', g);
        piezas[`${deck}.modo.${principal}`] = piezas[`${deck}.modo.${secundario}`] = { g, rotulo: t, textos: [r1, r2], par: [principal, secundario] };
        interactivo(g, `${deck}.modo.${principal}`);
      });
    }

    // Deck A (izquierda)
    faderVertical('A.tempo', 40, 56, 206, 'Tempo');
    texto(40, 300, 'A', 'letra', svg);
    jog('A', 192, 134);
    boton('A.sync', 73, 271, 62, 30, 'Sync');
    boton('A.cue', 161, 271, 62, 30, 'Cue');
    boton('A.play', 249, 271, 62, 30, 'Play');
    boton('A.pfl', 318, 24, 70, 22, 'PFL');
    boton('shift', 318, 56, 70, 22, 'Shift');
    perilla('master', 435, 63, 18, 'Master');
    modos('A', 333, 116);
    pads('A', 333, 152);
    // Mezclador
    redondo('bassfilter', 600, 34, 13, 'Bass/Filter');
    perilla('A.volumen', 540, 96, 22, 'Volume');
    perilla('B.volumen', 660, 96, 22, 'Volume');
    perilla('A.eq', 540, 182, 22, 'Bass');
    perilla('B.eq', 660, 182, 22, 'Bass');
    faderHorizontal('crossfader', 520, 680, 272, 'Crossfader');
    // Deck B (derecha)
    perilla('audifonos', 765, 63, 18, 'Headphones');
    boton('B.pfl', 812, 24, 70, 22, 'PFL');
    boton('vinyl', 812, 56, 70, 22, 'Vinyl');
    modos('B', 747, 116);
    pads('B', 747, 152);
    jog('B', 1008, 134);
    boton('B.sync', 889, 271, 62, 30, 'Sync');
    boton('B.cue', 977, 271, 62, 30, 'Cue');
    boton('B.play', 1065, 271, 62, 30, 'Play');
    faderVertical('B.tempo', 1160, 56, 206, 'Tempo');
    texto(1160, 300, 'B', 'letra', svg);

    // Qué se puede tocar ahora. etiqueta(nombre) da el texto para lectores de pantalla.
    function tocables(ids, etiqueta = n => n) {
      for (const [id, g, nombre] of grupos) {
        const si = ids === true || ids.has(id);
        g.classList.toggle('tocable', si);
        if (si) { g.setAttribute('role', 'button'); g.setAttribute('tabindex', '0'); g.setAttribute('aria-label', etiqueta(nombre, id)); }
        else { g.removeAttribute('role'); g.removeAttribute('tabindex'); g.removeAttribute('aria-label'); }
      }
    }
    // Pone una clase (asignado, elegido) en los controles de la lista y la quita de los demás
    function marcar(clase, ids) {
      for (const [id, g] of grupos) g.classList.toggle(clase, ids.has(id));
    }
    return { piezas, franja, tocables, marcar, ids: grupos.map(x => x[0]) };
  }

  window.StarlightDibujo = { dibujar, nombreControl };
})();
