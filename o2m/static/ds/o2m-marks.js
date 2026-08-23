/* ============================================================================
   O2M — MARKS  ·  v1.7  ·  Living medias
   v1.7 — O2M.actuator(name) + [data-o2m-actuator] : le jeu de glyphes des quatre
     catégories (silhouettes pleines) et du méta-bouton All (le bullseye).
   Framework-free renderer for the mark family and the generated cover system.
   Every shape is drawn with ramp CLASSES, never hard-coded colour, so the output
   follows whatever theme is active on <html data-theme="…">.

   Requires o2m.css (it owns --ring-a-* / --ring-b-*).
   Usage:
     <span data-o2m-mark="core" style="width:64px"></span>
     <div  data-o2m-cover="sequence" style="width:200px"></div>
     O2M.mount();                      // hydrate every data-o2m-* in the page
     el.innerHTML = O2M.mark('reduced');
     el.innerHTML = O2M.cover('graph');
   ========================================================================== */
(function (root) {
  'use strict';

  var RINGS = 5;                       /* the ramps define exactly five steps */

  /* Concentric half-discs. side: 'a' (ink, upper) | 'b' (accent, lower) */
  function halfRings(cx, cy, r, side, n, up) {
    n = Math.min(n || RINGS, RINGS);
    var out = '', i, ri, sweep = up ? 1 : 0;
    for (i = 0; i < n; i++) {
      ri = +(r * (1 - i / n)).toFixed(2);
      out += '<path class="ring-' + side + '-' + (i + 1) + '" d="M' + (cx - ri) + ' ' + cy +
             'A' + ri + ' ' + ri + ' 0 0 ' + sweep + ' ' + (cx + ri) + ' ' + cy + 'Z"/>';
    }
    return out;
  }

  /* Full bullseye: ink above, accent below (classes let --alt swap them) */
  function bullseye(cx, cy, r, n) {
    n = Math.min(n || RINGS, RINGS);
    var out = '', i, ri;
    for (i = 0; i < n; i++) {
      ri = +(r * (1 - i / n)).toFixed(2);
      out += '<path class="ring-top-' + (i + 1) + '" d="M' + (cx - ri) + ' ' + cy +
             'A' + ri + ' ' + ri + ' 0 0 1 ' + (cx + ri) + ' ' + cy + 'Z"/>';
    }
    for (i = 0; i < n; i++) {
      ri = +(r * (1 - i / n)).toFixed(2);
      out += '<path class="ring-bot-' + (i + 1) + '" d="M' + (cx - ri) + ' ' + cy +
             'A' + ri + ' ' + ri + ' 0 0 0 ' + (cx + ri) + ' ' + cy + 'Z"/>';
    }
    return out;
  }

  /* The horizon. Kind 'gap' = the void between halves; 'ink' = a drawn baseline. */
  function horizon(x1, x2, y, t, kind) {
    var cls = kind === 'ink' ? 'horizon horizon--ink' : 'horizon';
    return '<rect class="' + cls + '" x="' + x1 + '" y="' + (y - t / 2) +
           '" width="' + (x2 - x1) + '" height="' + t + '"/>';
  }

  function wrap(vb, inner, alt, style) {
    return '<svg class="o2m-bullseye' + (alt ? ' o2m-bullseye--alt' : '') +
           '" viewBox="' + vb + '" style="display:block;width:100%;height:auto;' +
           (style || '') + '">' + inner + '</svg>';
  }

  /* ── The mark family ─────────────────────────────────────────────────────── */
  var MARKS = {
    /* full bullseye — the core mark, 32px and up */
    core: function (alt) {
      return wrap('0 0 120 120', bullseye(60, 60, 56) + horizon(0, 120, 60, 2.6), alt);
    },
    /* half + heavy ink baseline — small sizes, headers, empty states */
    reduced: function (alt) {
      return wrap('0 0 120 70',
        halfRings(60, 60, 56, alt ? 'a' : 'b', RINGS, true) + horizon(2, 118, 62, 6, 'ink'), false);
    },
    /* four tangent discs, alternating polarity — lists, loading, rhythm */
    sequence: function () {
      var r = 28, s = '', i, cx;
      for (i = 0; i < 4; i++) {
        cx = r + i * r * 2;
        s += '<g' + (i % 2 ? ' class="o2m-bullseye--alt"' : '') + '>' + bullseye(cx, 32, r, 4) + '</g>';
      }
      return wrap('0 0 ' + (r * 8) + ' 64', s + horizon(0, r * 8, 32, 1.8));
    },
    /* nodes joined by hairlines — the playlist as a network */
    graph: function () {
      return wrap('0 0 224 124',
        bullseye(38, 40, 34, 4) + horizon(4, 72, 40, 1.8) +
        bullseye(112, 86, 34, 4) + horizon(78, 146, 86, 1.8) +
        bullseye(186, 34, 26, 4) + horizon(160, 212, 34, 1.8) +
        '<path class="o2m-bullseye-link" d="M38 40L112 86L186 34"/>' +
        '<circle class="o2m-bullseye-node" cx="38" cy="40" r="6"/>' +
        '<circle class="o2m-bullseye-node" cx="112" cy="86" r="6"/>' +
        '<circle class="o2m-bullseye-node" cx="186" cy="34" r="6"/>');
    },
    /* app icon — bullseye on --surface with a maskable safe area */
    icon: function () {
      return wrap('0 0 120 120',
        '<rect width="120" height="120" fill="var(--surface)"/>' +
        bullseye(60, 60, 34) +
        '<rect x="18" y="58.7" width="84" height="2.6" fill="var(--surface)"/>');
    }
  };

  /* ── Actuator glyphs ──────────────────────────────────────────────────────
     Le jeu retenu : mêmes formes que les silhouettes, mais dessinées au TRAIT FIN
     (1.4 sur grille 24, contre 2 pour l'iconographie générale) — les actionneurs
     sont grands et peu nombreux, ils n'ont pas besoin du poids d'une icône de
     barre ; le trait fin les rend plus calmes et laisse le mot porter.
     Le méta-bouton All garde le BULLSEYE — le seul bouton dont le sens EST la marque.
     Construction : stroke="currentColor", aucun fill sauf les noyaux pleins.
     Ne jamais fermer une contreforme avec var(--bg) : le glyphe doit rester juste
     quand le bouton passe en accent (.o2m-actuator.is-on / .o2m-all.is-on). */
  var ACT_W = 1.4;
  function actSvg(inner) {
    return '<svg class="o2m-actuator-glyph" viewBox="0 0 24 24" fill="none" ' +
           'stroke="currentColor" stroke-width="' + ACT_W + '" stroke-linecap="round" ' +
           'stroke-linejoin="round" aria-hidden="true">' + inner + '</svg>';
  }
  function ring(cx, cy, r) {
    return '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '"/>';
  }
  function dot(cx, cy, r) {
    return '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="currentColor" stroke="none"/>';
  }
  var ACTUATORS = {
    /* tête de note pleine (la seule masse du jeu) + hampe */
    /* La hampe part de x=11.9 (et non 12.7, le bord exact du cercle) et s'arrête à
       y=17 : son bout arrondi de 1,4 d'épaisseur reste ainsi DANS la tête de note.
       À 12.7/17.6 il dépassait en bas à droite — tout point à x=12.7 hors du centre
       est déjà hors du cercle. À remonter dans le design system. */
    music:   dot(8.4, 17.6, 4.3) + '<path d="M11.9 17V2.6"/>',
    /* capsule + dôme d'écoute */
    podcast: '<rect x="9.4" y="2.2" width="5.2" height="11.2" rx="2.6"/>' +
             '<path d="M4.6 11.6a7.4 7.4 0 0 0 14.8 0"/>',
    /* cercle + « i » */
    info:    ring(12, 12, 9.4) + dot(12, 7.7, 1.15) + '<path d="M12 11.2v5.6"/>',
    /* noyau + deux arcs : l'onde qui s'éloigne de l'objet */
    radio:   dot(12, 12, 1.9) +
             '<path d="M7.9 7.9a5.8 5.8 0 0 0 0 8.2M16.1 16.1a5.8 5.8 0 0 0 0-8.2"/>' +
             '<path d="M4.7 4.7a10.3 10.3 0 0 0 0 14.6M19.3 19.3a10.3 10.3 0 0 0 0-14.6"/>',
    /* la marque : bullseye au trait, coupé par l'horizon */
    all:     ring(12, 12, 9.6) + ring(12, 12, 5.6) + dot(12, 12, 1.7)
  };

  /* ── Generated cover system ──────────────────────────────────────────────── */
  var COVERS = {
    core: function () {
      return cov('var(--surface)', bullseye(100, 100, 72) + gapAt(0, 200, 100, 3, 'var(--surface)'));
    },
    bleed: function () {
      return cov('var(--bg)', bullseye(58, 66, 86) + gapAt(0, 200, 66, 3, 'var(--bg)'));
    },
    sequence: function () {
      var r = 25, s = '', i, cx;
      for (i = 0; i < 4; i++) {
        cx = r + i * r * 2;
        s += '<g' + (i % 2 ? ' class="o2m-bullseye--alt"' : '') + '>' + bullseye(cx, 100, r, 4) + '</g>';
      }
      return cov('var(--surface)', s + gapAt(0, 200, 100, 2, 'var(--surface)'));
    },
    arcs: function () {
      var R = [96, 78, 60, 42, 24], s = '';
      R.forEach(function (r, i) {
        s += '<path class="ring-' + (i % 2 ? 'b' : 'a') + '-' + (i + 1) +
             '" d="M' + (100 - r) + ' 168A' + r + ' ' + r + ' 0 0 1 ' + (100 + r) + ' 168Z"/>';
      });
      return cov('var(--surface)', s);
    },
    dots: function () {
      var g = 200 / 7, s = '', x, y;
      for (y = 0; y < 7; y++) for (x = 0; x < 7; x++) {
        s += '<circle class="ring-' + ((x + y) % 2 ? 'b' : 'a') + '-1" cx="' +
             (x * g + g / 2).toFixed(1) + '" cy="' + (y * g + g / 2).toFixed(1) +
             '" r="' + (g * 0.27).toFixed(1) + '"/>';
      }
      return cov('var(--surface)', s);
    },
    bands: function () {
      return cov('var(--bg)',
        '<rect width="200" height="200" class="ring-b-1"/>' +
        '<rect x="66" y="0" width="68" height="200" fill="var(--bg)"/>' +
        bullseye(100, 100, 34, 4) + gapAt(66, 134, 100, 2, 'var(--bg)'));
    },
    graph: function () {
      var g = 'var(--bg)';
      return cov('var(--surface)',
        bullseye(52, 58, 34, 4) + gapAt(14, 90, 58, 2, 'var(--surface)') +
        bullseye(140, 124, 34, 4) + gapAt(102, 178, 124, 2, 'var(--surface)') +
        '<path stroke="' + g + '" stroke-width="3" fill="none" d="M52 58L140 124"/>' +
        '<circle cx="52" cy="58" r="7" fill="' + g + '"/>' +
        '<circle cx="140" cy="124" r="7" fill="' + g + '"/>');
    },
    pills: function () {
      var B = 'var(--bg)';
      return cov(B,
        '<path class="ring-a-1" d="M18 58a40 40 0 0 1 80 0v84a40 40 0 0 1-80 0z"/>' +
        halfRings(58, 58, 40, 'b', 4, true) +
        '<path class="ring-b-1" d="M112 58a40 40 0 0 1 80 0v84a40 40 0 0 1-80 0z"/>' +
        halfRings(152, 142, 40, 'a', 4, false) +
        '<path stroke="' + B + '" stroke-width="3" fill="none" d="M58 142h94"/>');
    }
  };

  function gapAt(x1, x2, y, t, fill) {
    return '<rect x="' + x1 + '" y="' + (y - t / 2) + '" width="' + (x2 - x1) +
           '" height="' + t + '" fill="' + fill + '"/>';
  }
  function cov(bg, inner) {
    return wrap('0 0 200 200', '<rect width="200" height="200" fill="' + bg + '"/>' + inner);
  }

  var COVER_KEYS = Object.keys(COVERS);
  var O2M;

  O2M = {
    RINGS: RINGS,
    markNames: Object.keys(MARKS),
    coverNames: COVER_KEYS,

    /** Mark markup. name: core | reduced | sequence | graph | icon */
    mark: function (name, alt) {
      var f = MARKS[name] || MARKS.core;
      return f(!!alt);
    },

    actuatorNames: Object.keys(ACTUATORS),

    /** Actuator glyph. name: music | podcast | info | radio | all */
    actuator: function (name) {
      return actSvg(ACTUATORS[name] || ACTUATORS.all);
    },

    /** Cover markup. name: core|bleed|sequence|arcs|dots|bands|graph|pills */
    cover: function (name) {
      var f = COVERS[name] || COVERS.core;
      return f();
    },

    /** The fallback composition when nothing identifies the item. */
    defaultCover: 'core',

    /** Deterministic cover for a track — same id always yields the same art.
        A missing or generic seed returns the full bullseye (`core`): the default
        artwork should read as the mark, not as one variation among eight. */
    coverFor: function (id) {
      var s = String(id == null ? '' : id).trim();
      if (!s || /^(o2m|default|none|null|undefined|unknown)$/i.test(s)) {
        return COVERS[O2M.defaultCover]();
      }
      var h = 0, i;
      for (i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) >>> 0;
      return COVERS[COVER_KEYS[h % COVER_KEYS.length]]();
    },

    /** Hydrate [data-o2m-mark] and [data-o2m-cover] in a root. */
    mount: function (root) {
      var scope = root || document;
      scope.querySelectorAll('[data-o2m-mark]').forEach(function (el) {
        el.innerHTML = O2M.mark(el.getAttribute('data-o2m-mark'),
                                el.hasAttribute('data-o2m-alt'));
      });
      /* Le glyphe se glisse DEVANT le libellé : l'étiquette reste dans le markup,
         et une deuxième hydratation ne l'écrase pas (garde o2mGlyph). */
      scope.querySelectorAll('[data-o2m-actuator]').forEach(function (el) {
        if (el.dataset.o2mGlyph) return;
        el.insertAdjacentHTML('afterbegin', O2M.actuator(el.getAttribute('data-o2m-actuator')));
        el.dataset.o2mGlyph = '1';
      });
      scope.querySelectorAll('[data-o2m-cover]').forEach(function (el) {
        var v = el.getAttribute('data-o2m-cover');
        el.innerHTML = v === 'auto'
          ? O2M.coverFor(el.getAttribute('data-o2m-seed') || el.id)
          : O2M.cover(v);
      });
    }
  };

  root.O2M = O2M;
  if (document.readyState !== 'loading') O2M.mount();
  else document.addEventListener('DOMContentLoaded', function () { O2M.mount(); });
})(window);
