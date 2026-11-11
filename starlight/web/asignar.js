// Panel para ver y cambiar lo que hace un control. Lo usan el editor y el tablero.
'use strict';
(function () {
  const el = (tag, props = {}, ...hijos) => {
    const e = Object.assign(document.createElement(tag), props);
    e.append(...hijos.filter(h => h !== null && h !== undefined && h !== false));
    return e;
  };
  const nombreControl = c => window.StarlightDibujo.nombreControl(c);

  const PALETA = { fucsia: [200, 0, 100], salmon: [200, 60, 60], rojo: [255, 0, 0], naranja: [255, 92, 0], amarillo: [255, 240, 16],
    lima: [118, 200, 16], verde: [0, 255, 0], aguamarina: [50, 255, 160], celeste: [16, 200, 255], azul: [0, 0, 255],
    indigo: [60, 40, 200], morado: [100, 0, 200] };
  const NOMBRE_COLOR = { salmon: 'Salmón', indigo: 'Índigo' };
  const nombreColor = c => NOMBRE_COLOR[c] || c.charAt(0).toUpperCase() + c.slice(1);
  const EFECTOS = [['fijo', 'Fijo'], ['parpadeo', 'Parpadea'], ['respira', 'Respira']];
  const EFECTO_TXT = { fijo: 'fija', parpadeo: 'parpadea', respira: 'respira' };

  // ------------------------------------------------------------------ controles y acciones
  function claseDe(c) {
    if (c.endsWith('.jog')) return 'jog';
    if (/\.(volumen|eq|tempo)$/.test(c) || ['crossfader', 'master', 'audifonos'].includes(c)) return 'continuo';
    if (c.includes('.pad')) return 'pad';
    return 'boton';
  }
  const CLASE_TXT = { jog: 'Jog: girar', continuo: 'Perilla o fader', pad: 'Pad', boton: 'Botón' };
  const POR_CLASE = { boton: ['teclas', 'multimedia', 'escribir', 'abrir', 'base', 'luz', 'perfil', 'casa'],
    pad: ['teclas', 'multimedia', 'escribir', 'abrir', 'base', 'luz', 'perfil', 'casa'],
    continuo: ['volumen', 'volumen_app', 'casa'], jog: ['rueda', 'flechas', 'zoom', 'casa'] };
  function accionesPara(control, cat) {
    const conLuz = new Set(cat.con_luz);
    return POR_CLASE[claseDe(control)].filter(t => t !== 'luz' || conLuz.has(control) || control.includes('.pad'));
  }
  // El control del dibujo que representa a otro (el jog, los botones de modo que van de a dos)
  function pieza(c) {
    if (c.endsWith('.jog.toque')) return c.slice(0, -6);
    if (c.endsWith('.modo.fx')) return c.replace('fx', 'hotcue');
    if (c.endsWith('.modo.sampler')) return c.replace('sampler', 'loop');
    return c;
  }
  const coincide = (patron, c) => new RegExp('^' + patron.replace(/[.+^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*') + '$').test(c);

  // ------------------------------------------------------------------ textos
  const TECLA_TXT = { ctrl: 'Ctrl', control: 'Ctrl', shift: 'Shift', alt: 'Alt', win: 'Win', enter: 'Enter', esc: 'Esc', tab: 'Tab',
    espacio: 'Espacio', space: 'Espacio', arriba: '↑', abajo: '↓', izquierda: '←', derecha: '→', inicio: 'Inicio', fin: 'Fin',
    supr: 'Supr', borrar: 'Borrar', repag: 'RePág', avpag: 'AvPág' };
  const teclaTxt = t => TECLA_TXT[String(t).toLowerCase()] || (t.length === 1 ? t.toUpperCase() : t.toUpperCase());
  function resumen(a, cat, perfiles) {
    const v = a.accion.valor, t = a.accion.tipo;
    switch (t) {
      case 'multimedia': return cat.multimedia[v] || 'Tecla multimedia';
      case 'teclas': return (v && v.length) ? v.map(teclaTxt).join(' + ') : 'Atajo sin teclas';
      case 'escribir': return v ? `Escribe «${String(v).replace(/\n$/, '')}»${String(v).endsWith('\n') ? ' y Enter' : ''}` : 'Escribir texto';
      case 'abrir': return v ? `Abre ${v}` : 'Abrir';
      case 'volumen': return 'Volumen de Windows';
      case 'volumen_app': return v ? `Volumen de ${v}` : 'Volumen de una app';
      case 'rueda': return v === 'horizontal' ? 'Desplaza a los lados' : 'Desplaza arriba y abajo';
      case 'flechas': return v === 'horizontal' ? 'Flechas a los lados' : 'Flechas arriba y abajo';
      case 'zoom': return 'Zoom';
      case 'base': return v ? `Base ${v.rgb ? v.rgb : nombreColor(v.color).toLowerCase()} ${EFECTO_TXT[v.efecto] || ''}`.trim() : 'Color de la base';
      case 'luz': return v === 'parpadeo' ? 'Hace titilar su luz' : 'Prende y apaga su luz';
      case 'perfil': { const p = (perfiles || []).find(x => x.clave === v); return `Pasa a ${p ? p.nombre : 'otro perfil'}`; }
      case 'claude_pad': return `Sesión u opción ${v || '?'}`;
      case 'claude_ir': return v === 'terminada' ? 'Ir a la sesión que terminó' : 'Ir a la sesión que te necesita';
      case 'claude_tecla': return v && v.teclas && v.teclas.length ? `${v.teclas.map(teclaTxt).join(' + ')} a Claude` : 'Tecla a Claude';
      case 'casa': {
        if (!v || !v.id) return 'Luces de la casa';
        const pct = n => `${Math.round(n * 100)} %`;
        switch (v.que) {
          case 'color': return `${v.nombre}: color ${v.rgb}`;
          case 'brillo': return typeof v.nivel === 'number' ? `${v.nombre}: brillo a ${pct(v.nivel)}` : `Brillo de ${v.nombre}`;
          case 'temperatura': return typeof v.nivel === 'number' ? `${v.nombre}: temperatura a ${pct(v.nivel)}` : `Temperatura de ${v.nombre}`;
          case 'volumen': return typeof v.nivel === 'number' ? `${v.nombre}: volumen a ${pct(v.nivel)}` : `Volumen de ${v.nombre}`;
          case 'subir': return `Sube ${v.nombre} ${v.paso || 10} %`;
          case 'bajar': return `Baja ${v.nombre} ${v.paso || 10} %`;
          case 'paso': return `Sube y baja ${v.nombre}`;
          case 'play': return `Play o pausa en ${v.nombre}`;
        }
        const que = { alternar: 'Prende o apaga', encender: 'Prende', apagar: 'Apaga', escena: 'Activa' }[v.que] || '';
        return `${que} ${v.nombre}`;
      }
    }
    return (cat.acciones[t] || {}).etiqueta || t;
  }
  function textoCuando(a, cat) {
    const partes = [];
    if (a.shift === true) partes.push('con Shift');
    if (a.shift === false && claseDe(a.control) !== 'continuo') partes.push('sin Shift');
    if (a.al === 'soltar') partes.push('al soltar');
    const si = a.si || {};
    if (si.claude) partes.push(`si Claude ${({ esperando: 'te necesita', no_esperando: 'no te necesita', trabajando: 'trabaja', listo: 'terminó' })[si.claude]}`);
    if (si.app && si.app.length) partes.push(`si ${si.app.join(' o ')} está al frente`);
    return partes.join(' · ');
  }

  // ------------------------------------------------------------------ piezas
  function seg(pares, actual, alCambiar, etiqueta, chico) {
    const s = el('div', { className: 'seg' + (chico ? ' chico' : '') });
    s.setAttribute('role', 'group');
    if (etiqueta) s.setAttribute('aria-label', etiqueta);
    for (const [v, t] of pares) {
      const b = el('button', { type: 'button', textContent: t });
      b.setAttribute('aria-pressed', String(String(v) === String(actual)));
      b.addEventListener('click', () => {
        s.querySelectorAll('button').forEach(x => x.setAttribute('aria-pressed', String(x === b)));
        alCambiar(v);
      });
      s.append(b);
    }
    return s;
  }
  // libre: { valor: '#rrggbb' o null, alCambiar(hex) } agrega un color libre con selector al final
  function muestras(actual, alCambiar, ninguna, libre) {
    const m = el('div', { className: 'muestras' });
    m.setAttribute('role', 'group');
    m.setAttribute('aria-label', 'Color');
    const marcar = elegida => m.querySelectorAll('.muestra').forEach(x => {
      if (x.tagName === 'BUTTON') x.setAttribute('aria-pressed', String(x === elegida));
      else x.classList.toggle('elegida', x === elegida);
    });
    const opciones = [...(ninguna ? [[null, ninguna]] : []), ...Object.keys(PALETA).map(c => [c, nombreColor(c)])];
    for (const [c, t] of opciones) {
      const b = el('button', { type: 'button', className: 'muestra' + (c ? '' : ' ninguna'), title: t });
      b.setAttribute('aria-label', t);
      if (c) b.style.setProperty('--m', `rgb(${PALETA[c].join(',')})`);
      b.setAttribute('aria-pressed', String(!(libre && libre.valor) && c === actual));
      b.addEventListener('click', () => { marcar(b); alCambiar(c); });
      m.append(b);
    }
    if (libre) {
      const entrada = el('input', { type: 'color', value: libre.valor || '#ff5a00' });
      entrada.setAttribute('aria-label', 'Color libre');
      const caja = el('label', { className: 'muestra libre-m' + (libre.valor ? ' elegida con-color' : ''), title: 'Color libre' }, entrada);
      if (libre.valor) caja.style.setProperty('--m', libre.valor);
      entrada.addEventListener('input', () => {
        caja.style.setProperty('--m', entrada.value); caja.classList.add('con-color'); marcar(caja); libre.alCambiar(entrada.value);
      });
      m.append(caja);
    }
    return m;
  }
  // Color de la base completo: color, efecto, intensidad y velocidad. v se edita en su lugar.
  // Sin tocar la intensidad o la velocidad, el perfil no las cambia («Sin cambiar»).
  const RANGO_RITMO = { parpadeo: [2.0, 0.12], respira: [6.0, 0.6] };   // segundos por ciclo: lento, rápido
  const POR_DEFECTO_RITMO = { parpadeo: 1.0, respira: 2.4 };
  const aSegundos = (ef, x) => { const [a, b] = RANGO_RITMO[ef]; return a * Math.pow(b / a, x / 100); };
  const aControl = (ef, s) => { const [a, b] = RANGO_RITMO[ef]; return Math.round(100 * Math.log(s / a) / Math.log(b / a)); };
  const coma = n => n.toFixed(1).replace('.', ',');
  const textoRitmo = (ef, s) => ef === 'parpadeo' ? `${coma(1 / s)} por segundo` : `una cada ${coma(s)} s`;
  function deslizador(etiqueta, min, max, valor, texto, alMover) {
    const r = el('input', { type: 'range', min, max, value: valor });
    r.setAttribute('aria-label', etiqueta);
    const salida = el('output', { className: 'valor-desliza', textContent: texto });
    r.addEventListener('input', () => { salida.textContent = alMover(+r.value); });
    return el('label', { className: 'desliza' }, el('span', { className: 'etq-desliza', textContent: etiqueta }), r, salida);
  }
  function colorBase(v, alCambiar, opciones = {}) {
    const caja = el('div', { className: 'color-base' });
    const pintar = () => {
      const efecto = seg(EFECTOS, v.efecto || 'fijo', e => { v.efecto = e; if (e === 'fijo') delete v.ciclo; alCambiar(); pintar(); }, 'Efecto', true);
      const intensidad = deslizador('Intensidad', 0, 100, typeof v.brillo === 'number' ? Math.round(v.brillo * 100) : 100,
        typeof v.brillo === 'number' ? `${Math.round(v.brillo * 100)} %` : 'Sin cambiar',
        x => { v.brillo = x / 100; alCambiar(); return `${x} %`; });
      const linea = el('div', { className: 'linea' }, efecto, intensidad);
      if (v.efecto && v.efecto !== 'fijo') {
        const ef = v.efecto, s = typeof v.ciclo === 'number' ? v.ciclo : POR_DEFECTO_RITMO[ef];
        linea.append(deslizador('Velocidad', 0, 100, aControl(ef, s), typeof v.ciclo === 'number' ? textoRitmo(ef, s) : 'Sin cambiar',
          x => { v.ciclo = Math.round(aSegundos(ef, x) * 1000) / 1000; alCambiar(); return textoRitmo(ef, v.ciclo); }));
      }
      const hijos = [muestras(v.color || null, c => {
        delete v.rgb; v.color = c;
        if (opciones.alColor) opciones.alColor(c);
        alCambiar();
      }, opciones.ninguna, { valor: v.rgb || null, alCambiar: hex => {
        const primera = !v.rgb && !v.color;
        delete v.color; v.rgb = hex; alCambiar();
        if (primera && opciones.alColor) opciones.alColor(hex);
      } })];
      if (v.color || v.rgb || !opciones.ninguna) hijos.push(linea);
      caja.replaceChildren(...hijos);
    };
    pintar();
    caja.repintar = pintar;
    return caja;
  }

  function vistaTeclas(lista) {
    const caja = el('span', { className: 'teclas' });
    (lista || []).forEach((t, i) => { if (i) caja.append(el('span', { className: 'mas', textContent: '+' })); caja.append(el('kbd', { className: 'tecla', textContent: teclaTxt(t) })); });
    return caja;
  }
  // Atajo: se graba presionándolo en el teclado (o se escribe, por ejemplo ctrl+shift+s)
  const DE_TECLADO = { Control: 'ctrl', Shift: 'shift', Alt: 'alt', Meta: 'win', Enter: 'enter', Escape: 'esc', Tab: 'tab', ' ': 'espacio',
    ArrowUp: 'arriba', ArrowDown: 'abajo', ArrowLeft: 'izquierda', ArrowRight: 'derecha', Home: 'inicio', End: 'fin', Delete: 'supr',
    Backspace: 'borrar', PageUp: 'rePag', PageDown: 'avPag' };
  function campoTeclas(acc, alCambiar) {
    const lista = Array.isArray(acc.valor) ? acc.valor : [];
    let vista = vistaTeclas(lista);
    const entrada = el('input', { type: 'text', className: 'campo-txt', value: lista.join('+'), placeholder: 'o escríbelo: ctrl+shift+s' });
    entrada.setAttribute('aria-label', 'Atajo escrito');
    entrada.style.width = '170px';
    const grabar = el('button', { type: 'button', className: 'boton-txt', textContent: 'Grabar atajo' });
    const poner = (teclas, desdeTexto) => {
      acc.valor = teclas;
      const n = vistaTeclas(teclas); vista.replaceWith(n); vista = n;
      if (!desdeTexto) entrada.value = teclas.join('+');
      alCambiar();
    };
    entrada.addEventListener('input', () => poner(entrada.value.split('+').map(x => x.trim()).filter(Boolean), true));
    let oyendo = null;
    const parar = () => { if (oyendo) document.removeEventListener('keydown', oyendo, true); oyendo = null; grabar.textContent = 'Grabar atajo'; grabar.classList.remove('primario'); };
    grabar.addEventListener('click', () => {
      if (oyendo) return parar();
      grabar.textContent = 'Presiona el atajo…'; grabar.classList.add('primario');
      oyendo = e => {
        e.preventDefault(); e.stopPropagation();
        const mods = [e.ctrlKey && 'ctrl', e.shiftKey && 'shift', e.altKey && 'alt', e.metaKey && 'win'].filter(Boolean);
        if (['Control', 'Shift', 'Alt', 'Meta'].includes(e.key)) return;  // falta la tecla principal
        let k = DE_TECLADO[e.key];
        if (!k && /^Key[A-Z]$/.test(e.code)) k = e.code.slice(3).toLowerCase();
        if (!k && /^Digit\d$/.test(e.code)) k = e.code.slice(5);
        if (!k && /^F\d{1,2}$/.test(e.key)) k = e.key.toLowerCase();
        if (!k) return;
        parar(); poner([...mods, k]);
      };
      document.addEventListener('keydown', oyendo, true);
    });
    // el atajo se ve como teclas; escribirlo a mano es la segunda opción
    entrada.hidden = true;
    const escribir = el('button', { type: 'button', className: 'enlace-boton', textContent: 'Escribirlo' });
    escribir.addEventListener('click', () => { entrada.hidden = false; escribir.hidden = true; entrada.focus(); });
    if (!lista.length) vista.hidden = false;
    return el('span', { className: 'linea' }, vista, grabar, escribir, entrada);
  }

  function campoValor(a, ctx, repintar) {
    const acc = a.accion, tipo = acc.tipo, cat = ctx.cat, cambio = ctx.alCambiar;
    const pide = (cat.acciones[tipo] || {}).valor;
    const texto = (ph, ancho) => {
      const i = el('input', { type: 'text', className: 'campo-txt', value: String(acc.valor || '').replace(/\n$/, ''), placeholder: ph });
      i.style.width = ancho; i.setAttribute('aria-label', cat.acciones[tipo].etiqueta);
      return i;
    };
    if (pide === 'multimedia') {
      if (!(acc.valor in cat.multimedia)) acc.valor = 'play_pausa';
      const s = el('select', { className: 'campo-txt' });
      s.setAttribute('aria-label', 'Tecla multimedia');
      for (const [v, t] of Object.entries(cat.multimedia)) s.add(new Option(t, v, false, v === acc.valor));
      s.addEventListener('change', () => { acc.valor = s.value; cambio(); });
      return s;
    }
    if (pide === 'teclas') return campoTeclas(acc, cambio);
    if (tipo === 'escribir') {
      const conEnter = String(acc.valor || '').endsWith('\n');
      const i = texto('Texto', '200px');
      let enter = conEnter;
      const fijar = () => { acc.valor = i.value + (enter ? '\n' : ''); cambio(); };
      i.addEventListener('input', fijar);
      return el('span', { className: 'linea' }, i, seg([[false, 'Solo escribir'], [true, 'Escribir y Enter']], conEnter, v => { enter = v; fijar(); }, 'Después de escribir', true));
    }
    if (pide === 'texto') {
      const i = texto({ abrir: 'https://… o C:\\…\\programa.exe', volumen_app: 'spotify' }[tipo] || '', tipo === 'abrir' ? '320px' : '180px');
      i.addEventListener('input', () => { acc.valor = i.value; cambio(); });
      return i;
    }
    if (pide === 'direccion') {
      if (!['vertical', 'horizontal'].includes(acc.valor)) acc.valor = 'vertical';
      return seg([['vertical', 'Arriba y abajo'], ['horizontal', 'A los lados']], acc.valor, v => { acc.valor = v; cambio(); }, 'Dirección', true);
    }
    if (pide === 'color') {
      const v = acc.valor && acc.valor.color ? acc.valor : (acc.valor = { color: 'naranja', efecto: 'fijo' });
      return colorBase(v, cambio);
    }
    if (pide === 'efecto_luz') {
      if (!['fijo', 'parpadeo'].includes(acc.valor)) acc.valor = 'fijo';
      return seg([['fijo', 'Prende y apaga'], ['parpadeo', 'Titila y apaga']], acc.valor, v => { acc.valor = v; cambio(); }, 'Cómo', true);
    }
    if (pide === 'perfil') {
      const otros = (ctx.perfiles || []).filter(p => p.clave !== ctx.clave);
      if (!otros.some(p => p.clave === acc.valor)) acc.valor = otros[0] ? otros[0].clave : null;
      return seg(otros.map(p => [p.clave, p.nombre]), acc.valor, v => { acc.valor = v; cambio(); }, 'Perfil', true);
    }
    if (pide === 'casa') return campoCasa(a, ctx);
    if (pide === 'claude_pad') {
      // 1-4 son los pads del deck A y 5-8 los del B; por defecto, el que corresponde a este pad
      const propio = /^([AB])\.pad([1-4])$/.exec(a.control);
      const sugerido = propio ? (propio[1] === 'A' ? 0 : 4) + Number(propio[2]) : 1;
      if (!(Number(acc.valor) >= 1 && Number(acc.valor) <= 8)) { acc.valor = sugerido; setTimeout(cambio); }
      const s = el('select', { className: 'campo-txt' });
      s.setAttribute('aria-label', 'Número de sesión u opción');
      for (let i = 1; i <= 8; i++) s.add(new Option(`Sesión u opción ${i}`, String(i), false, i === Number(acc.valor)));
      s.addEventListener('change', () => { acc.valor = Number(s.value); cambio(); });
      return s;
    }
    if (pide === 'claude_ir') {
      if (!(acc.valor in cat.claude_ir)) { acc.valor = 'espera'; setTimeout(cambio); }
      return seg(Object.entries(cat.claude_ir), acc.valor, v => { acc.valor = v; cambio(); }, 'A cuál', true);
    }
    if (pide === 'claude_tecla') {
      if (!acc.valor || typeof acc.valor !== 'object' || Array.isArray(acc.valor)) { acc.valor = { teclas: ['esc'], luz: 'interrumpir' }; setTimeout(cambio); }
      const v = acc.valor;
      if (!(v.luz in cat.luz_claude)) v.luz = 'sesion';
      const atajo = { valor: v.teclas || [] };  // campoTeclas edita .valor
      const teclas = campoTeclas(atajo, () => { v.teclas = atajo.valor; cambio(); });
      return el('span', { className: 'linea' }, teclas,
        seg(Object.entries(cat.luz_claude), v.luz, x => { v.luz = x; cambio(); }, 'Su luz se prende', true));
    }
    acc.valor = null;
    return el('span', { className: 'ayuda-linea', textContent: cat.acciones[tipo].ayuda });
  }

  // Luces de la casa: qué cosa, y qué hacer con ella según lo que sabe hacer y según el control
  const QUE_CASA = { alternar: 'Prende o apaga', encender: 'Prende', apagar: 'Apaga', brillo: 'Brillo a…', subir: 'Sube', bajar: 'Baja',
    color: 'Color', temperatura: 'Temperatura', play: 'Play o pausa', volumen: 'Volumen a…', paso: 'Sube y baja', escena: 'Activa' };
  function opcionesCasa(cosa, clase) {
    const puede = (cosa && cosa.puede) || ['onoff'];
    if (clase === 'continuo') return ['brillo', 'temperatura', 'volumen'].filter(q => puede.includes(q));
    if (clase === 'jog') return puede.includes('brillo') || puede.includes('volumen') ? ['paso'] : [];
    if (puede.includes('activar')) return ['escena'];
    if (puede.includes('play')) return ['play', 'subir', 'bajar'];
    return ['alternar', 'encender', 'apagar', ...(puede.includes('brillo') ? ['brillo', 'subir', 'bajar'] : []),
      ...(puede.includes('color') ? ['color'] : []), ...(puede.includes('temperatura') ? ['temperatura'] : [])];
  }
  function campoCasa(a, ctx) {
    const acc = a.accion, cambio = ctx.alCambiar, clase = claseDe(a.control);
    const cosas = (ctx.casa || []).filter(c => opcionesCasa(c, clase).length);
    if (!cosas.length) {
      const enlace = el('a', { href: 'casa', textContent: (ctx.casa || []).length ? 'Ninguna cosa de la casa' : 'Conecta Home Assistant o el puente Hue' });
      const resto = (ctx.casa || []).length
        ? (clase === 'jog' ? ' sube y baja con el jog.' : ' se maneja con una perilla.')
        : ' para usar sus luces, escenas y reproductores.';
      return el('span', { className: 'ayuda-linea' }, enlace, resto);
    }
    if (!(acc.valor && acc.valor.id)) {
      // primero una luz (en Hue, que responde más rápido), luego lo demás
      const peso = c => (c.tipo === 'luz' ? 0 : c.tipo === 'aparato' ? 1 : c.tipo === 'reproductor' ? 2 : 3) + (c.donde === 'hue' ? 0 : 0.5);
      const c = [...cosas].sort((x, y) => peso(x) - peso(y))[0];
      acc.valor = { donde: c.donde, id: c.id, nombre: c.nombre, que: opcionesCasa(c, clase)[0] };
      setTimeout(cambio);  // que el resumen y el aviso de cambios sin guardar se enteren
    }
    const v = acc.valor;
    const caja = el('span', { className: 'color-base' });
    const pintar = () => {
      const cosa = cosas.find(c => c.donde === v.donde && c.id === v.id);
      const opciones = opcionesCasa(cosa, clase);
      if (cosa && !opciones.includes(v.que)) v.que = opciones[0];
      // qué cosa
      const s = el('select', { className: 'campo-txt' });
      s.setAttribute('aria-label', 'Qué cosa de la casa');
      for (const [d, t] of [['hue', 'Hue'], ['ha', 'Home Assistant']]) {
        const lista = cosas.filter(c => c.donde === d);
        if (!lista.length) continue;
        const g = el('optgroup', { label: t });
        lista.forEach(c => g.append(new Option(`${c.nombre} · ${c.clase.toLowerCase()}`, `${c.donde}|${c.id}`, false, c.donde === v.donde && c.id === v.id)));
        s.append(g);
      }
      if (!cosa) s.prepend(new Option(`${v.nombre} (no la encuentro)`, `${v.donde}|${v.id}`, true, true));
      s.addEventListener('change', () => {
        const [d, ...resto] = s.value.split('|'); const c = cosas.find(x => x.donde === d && x.id === resto.join('|'));
        Object.assign(v, { donde: d, id: c.id, nombre: c.nombre });
        if (!opcionesCasa(c, clase).includes(v.que)) v.que = opcionesCasa(c, clase)[0];
        cambio(); pintar();
      });
      const linea1 = el('div', { className: 'linea' }, s);
      const etiqueta = q => clase === 'continuo' ? ({ brillo: 'Brillo', temperatura: 'Temperatura', volumen: 'Volumen' }[q]) : QUE_CASA[q];
      if (opciones.length > 1) linea1.append(seg(opciones.map(q => [q, etiqueta(q)]), v.que, q => { v.que = q; cambio(); pintar(); }, 'Qué hacer', true));
      const hijos = [linea1];
      // el detalle de cada orden
      const linea2 = el('div', { className: 'linea' });
      if (clase === 'continuo') {
        delete v.nivel;
        linea2.append(el('span', { className: 'ayuda-linea', textContent: v.que === 'temperatura' ? 'Abajo, luz cálida; arriba, fría.' : 'La posición de la perilla es el nivel.' }));
      } else if (clase === 'jog') {
        if (![1, 2, 5].includes(v.paso)) v.paso = 2;
        linea2.append(el('span', { className: 'ayuda-linea', textContent: 'Cada paso del jog:' }),
          seg([[1, 'Fino · 1 %'], [2, 'Medio · 2 %'], [5, 'Rápido · 5 %']], v.paso, x => { v.paso = x; cambio(); }, 'Cuánto por paso', true));
      } else if (['brillo', 'temperatura', 'volumen'].includes(v.que)) {
        if (typeof v.nivel !== 'number') v.nivel = 0.6;
        const r = el('input', { type: 'range', min: 0, max: 100, value: Math.round(v.nivel * 100) });
        r.setAttribute('aria-label', 'Nivel');
        const texto = x => v.que === 'temperatura' ? (x < 34 ? 'Cálida' : x > 66 ? 'Fría' : 'Neutra') + ` · ${x} %` : `${x} %`;
        const salida = el('output', { className: 'valor-desliza', textContent: texto(+r.value) });
        r.addEventListener('input', () => { v.nivel = +r.value / 100; salida.textContent = texto(+r.value); cambio(); });
        linea2.append(el('label', { className: 'desliza' }, el('span', { className: 'etq-desliza', textContent: 'Lo deja en' }), r, salida));
      } else if (v.que === 'subir' || v.que === 'bajar') {
        if (![5, 10, 25].includes(v.paso)) v.paso = 10;
        linea2.append(el('span', { className: 'ayuda-linea', textContent: 'Cada vez:' }),
          seg([[5, '5 %'], [10, '10 %'], [25, '25 %']], v.paso, x => { v.paso = x; cambio(); }, 'Cuánto cada vez', true));
      } else if (v.que === 'color') {
        if (!v.rgb) v.rgb = '#ff5a00';
        const actual = Object.entries(PALETA).find(([, rgb]) => '#' + rgb.map(x => x.toString(16).padStart(2, '0')).join('') === v.rgb);
        linea2.append(muestras(actual ? actual[0] : null, c => { v.rgb = '#' + PALETA[c].map(x => x.toString(16).padStart(2, '0')).join(''); cambio(); },
          null, { valor: actual ? null : v.rgb, alCambiar: hex => { v.rgb = hex; cambio(); } }));
      }
      if (v.que !== 'color') delete v.rgb;
      if (!['subir', 'bajar', 'paso'].includes(v.que)) delete v.paso;
      if (linea2.childNodes.length) hijos.push(linea2);
      caja.replaceChildren(...hijos);
    };
    pintar();
    return caja;
  }

  function filaAccion(a, ctx, quitar, repintar) {
    const cat = ctx.cat, clase = claseDe(a.control), cambio = ctx.alCambiar;
    const caja = el('div', { className: 'accion' });
    // qué hace
    const tipos = accionesPara(a.control, cat);
    if (!tipos.includes(a.accion.tipo)) a.accion = { tipo: tipos[0], valor: null };
    const tipo = el('select', { className: 'campo-txt' });
    tipo.setAttribute('aria-label', 'Qué hace');
    for (const t of tipos) tipo.add(new Option(cat.acciones[t].etiqueta, t, false, t === a.accion.tipo));
    tipo.addEventListener('change', () => { a.accion = { tipo: tipo.value, valor: null }; cambio(); repintar(); });
    const q = el('button', { type: 'button', className: 'enlace-boton quitar', textContent: 'Quitar' });
    q.addEventListener('click', quitar);
    caja.append(el('div', { className: 'linea' }, el('span', { className: 'etq-linea', textContent: 'Hace' }), tipo, campoValor(a, ctx, repintar), q));
    // cuándo
    const cuando = [];
    if (clase === 'boton' || clase === 'pad') {
      if (a.al === 'siempre') a.al = 'presionar';
      cuando.push(seg([['presionar', 'Al presionar'], ['soltar', 'Al soltar']], a.al, v => { a.al = v; cambio(); }, 'Cuándo', true));
    } else a.al = 'siempre';
    cuando.push(seg([['', 'Con o sin Shift'], ['true', 'Solo con Shift'], ['false', 'Solo sin Shift']], a.shift === null || a.shift === undefined ? '' : String(a.shift),
      v => { a.shift = v === '' ? null : v === 'true'; cambio(); }, 'Shift', true));
    caja.append(el('div', { className: 'linea' }, el('span', { className: 'etq-linea', textContent: 'Cuándo' }), ...cuando));
    // solo si
    const si = a.si || {};
    if (a._conSi || si.claude || (si.app && si.app.length)) {
      const app = el('input', { type: 'text', className: 'campo-txt', value: (si.app || []).join(', '), placeholder: 'wave, chrome, spotify' });
      app.style.width = '190px';
      app.setAttribute('aria-label', 'Programa al frente');
      app.addEventListener('input', () => {
        a.si = a.si || {};
        a.si.app = app.value.split(',').map(x => x.trim().toLowerCase()).filter(Boolean);
        cambio();
      });
      const claude = seg([['', 'Da igual'], ...Object.entries(cat.si_claude)], si.claude || '', v => { a.si = a.si || {}; a.si.claude = v || null; cambio(); }, 'Estado de Claude Code', true);
      caja.append(el('div', { className: 'linea' }, el('span', { className: 'etq-linea', textContent: 'Claude' }), claude),
        el('div', { className: 'linea' }, el('span', { className: 'etq-linea', textContent: 'Al frente' }), app,
          el('span', { className: 'ayuda-linea', textContent: 'Solo si tienes al frente ese programa. Vacío: cualquiera.' })));
    } else {
      const agregar = el('button', { type: 'button', className: 'enlace-boton', textContent: 'Solo si… (Claude Code o el programa al frente)' });
      agregar.addEventListener('click', () => { a._conSi = true; repintar(); });
      caja.append(el('div', { className: 'linea' }, el('span', { className: 'etq-linea', textContent: '' }), agregar));
    }
    return caja;
  }

  // ctx: { control, asignaciones (se edita en su lugar), manejadores (perfil en Python), tipo, cat, perfiles, clave,
  //        alCambiar(), alElegir(control) }
  function panel(contenedor, ctx) {
    const pintar = () => {
      const c = ctx.control, cat = ctx.cat;
      const titulo = el('div', { className: 'titulo' }, el('h3', { textContent: nombreControl(c) }),
        el('span', { className: 'clase', textContent: c.endsWith('.jog.toque') ? 'Jog: tocar arriba' : CLASE_TXT[claseDe(c)] }));
      // el jog se gira o se toca; los botones de modo valen por dos
      const base = pieza(c);
      if (base.endsWith('.jog')) titulo.append(el('span', { className: 'alterna' }, seg([[base, 'Girar'], [base + '.toque', 'Tocar arriba']], c, v => ctx.alElegir(v), 'Parte del jog', true)));
      if (/\.modo\.(hotcue|loop)$/.test(base)) {
        const otro = base.endsWith('hotcue') ? base.replace('hotcue', 'fx') : base.replace('loop', 'sampler');
        titulo.append(el('span', { className: 'alterna' }, seg([[base, nombreControl(base).split(' ')[0] === 'Hot' ? 'Hot Cue' : 'Loop'], [otro, nombreControl(otro).split(' ')[0]]], c, v => ctx.alElegir(v), 'Botón de modo', true)));
      }
      const partes = [titulo];
      // lo que hace el perfil en Python, y si un cambio tuyo lo reemplaza
      const propias = ctx.asignaciones.filter(a => a.control === c);
      const delPerfil = (ctx.manejadores || []).filter(m => coincide(m.control, c));
      if (delPerfil.length) {
        const ul = el('ul', { className: 'del-perfil' });
        for (const m of delPerfil) {
          const tapado = propias.some(a => a.shift === null || a.shift === undefined || a.shift === m.shift || m.shift === null);
          const li = el('li', { className: tapado ? 'reemplazado' : '' }, el('span', { className: 'quien', textContent: 'Del perfil' }),
            el('span', { textContent: m.descripcion + (m.shift === true ? ' · con Shift' : m.shift === false ? ' · sin Shift' : '') }));
          if (tapado) li.title = 'Lo reemplaza tu cambio';
          ul.append(li);
        }
        partes.push(ul);
      }
      for (const a of propias) {
        partes.push(filaAccion(a, ctx, () => { ctx.asignaciones.splice(ctx.asignaciones.indexOf(a), 1); ctx.alCambiar(); pintar(); }, pintar));
      }
      if (!propias.length && !delPerfil.length) partes.push(el('p', { className: 'vacio-control', textContent: 'Este control todavía no hace nada en este perfil.' }));
      const agregar = el('button', { type: 'button', className: 'boton-txt', textContent: propias.length ? 'Agregar otra acción' : (delPerfil.length ? 'Cambiar lo que hace' : 'Agregar una acción') });
      agregar.addEventListener('click', () => {
        const t = accionesPara(c, cat)[0];
        ctx.asignaciones.push({ control: c, al: claseDe(c) === 'boton' || claseDe(c) === 'pad' ? 'presionar' : 'siempre', shift: null, accion: { tipo: t, valor: null } });
        ctx.alCambiar(); pintar();
      });
      partes.push(el('div', {}, agregar));
      contenedor.replaceChildren(el('div', { className: 'panel-control' }, ...partes));
    };
    pintar();
    return { repintar: pintar };
  }

  // Controles con algo asignado, como piezas del dibujo
  function asignados(asignaciones, manejadores, ids) {
    const s = new Set(asignaciones.filter(a => a.control).map(a => pieza(a.control)));
    for (const m of manejadores || []) for (const id of ids) if (coincide(m.control, id) || coincide(m.control, id + '.toque')) s.add(id);
    return s;
  }
  // Copia sin las marcas de la página (_conSi), lista para guardar
  const limpiar = lista => lista.filter(a => a.control).map(({ _conSi, ...a }) => {
    if (a.si) { const si = {}; if (a.si.claude) si.claude = a.si.claude; if (a.si.app && a.si.app.length) si.app = a.si.app; a.si = Object.keys(si).length ? si : undefined; }
    if (!a.si) delete a.si;
    return a;
  });

  window.Asignar = { panel, seg, muestras, colorBase, resumen, textoCuando, claseDe, pieza, coincide, asignados, limpiar, nombreColor, PALETA, EFECTOS, vistaTeclas, el };
})();
