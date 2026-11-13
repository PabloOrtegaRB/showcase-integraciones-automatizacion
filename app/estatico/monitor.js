// Monitor de integraciones: consulta la API y muestra órdenes, indicadores y eventos.
// Usa textContent (nunca innerHTML con datos) para evitar inyección de HTML.
(function () {
  "use strict";
  var ETIQUETAS = { PENDIENTE: "Pendiente", ENVIADA: "Enviada", ASIGNADA: "Asignada", COMPLETADA: "Completada", ERROR_INTEGRACION: "Error de integración" };
  var SERVICIOS = { MANTENCION_PREVENTIVA: "Mantención preventiva", MANTENCION_CORRECTIVA: "Mantención correctiva", CLIMATIZACION: "Climatización", ELECTRICIDAD: "Electricidad", INSPECCION: "Inspección" };
  var MALOS = ["ENVIO_FALLIDO", "ENVIO_AGOTADO", "ENVIO_RECHAZADO", "WEBHOOK_RECHAZADO"];
  var AVISOS = ["WEBHOOK_DUPLICADO", "REINTENTO_MANUAL", "ENVIO_INTENTO"];
  var filtro = document.getElementById("filtro-estado");

  function el(tag, clase, texto) {
    var nodo = document.createElement(tag);
    if (clase) nodo.className = clase;
    if (texto !== undefined && texto !== null) nodo.textContent = String(texto);
    return nodo;
  }

  function hora(iso) {
    try { return new Date(iso).toLocaleTimeString("es-CL"); } catch (e) { return iso; }
  }

  function json(url, opciones) {
    return fetch(url, opciones).then(function (r) {
      return r.json().then(function (cuerpo) { return { ok: r.ok, cuerpo: cuerpo }; });
    });
  }

  function pintarResumen(r) {
    var porEstado = r.por_estado || {};
    document.getElementById("kpi-total").textContent = r.total;
    document.getElementById("kpi-entregadas").textContent = r.entregadas_al_proveedor;
    document.getElementById("kpi-completadas").textContent = porEstado.COMPLETADA || 0;
    document.getElementById("kpi-error").textContent = r.con_error;
    document.getElementById("kpi-reintentos").textContent = r.fallas_transitorias;
    document.getElementById("kpi-intentos").textContent = r.promedio_intentos === null ? "—" : String(r.promedio_intentos).replace(".", ",");
  }

  function pintarOrdenes(datos) {
    var cuerpo = document.getElementById("tabla-ordenes");
    cuerpo.replaceChildren();
    if (!datos.contenido.length) {
      var fila = el("tr"); var celda = el("td", "vacio", "No hay órdenes con este filtro."); celda.colSpan = 7; fila.appendChild(celda); cuerpo.appendChild(fila);
      return;
    }
    datos.contenido.forEach(function (o) {
      var fila = el("tr");
      var codigo = el("td"); codigo.appendChild(el("code", null, o.codigo)); fila.appendChild(codigo);
      fila.appendChild(el("td", null, o.cliente));
      fila.appendChild(el("td", null, SERVICIOS[o.servicio] || o.servicio));
      var estado = el("td"); var insignia = el("span", "estado e-" + o.estado, ETIQUETAS[o.estado] || o.estado);
      if (o.ultimo_error) insignia.title = o.ultimo_error;
      estado.appendChild(insignia); fila.appendChild(estado);
      fila.appendChild(el("td", null, o.intentos));
      fila.appendChild(el("td", null, o.referencia_externa || "—"));
      var acciones = el("td");
      if (o.estado === "ERROR_INTEGRACION") {
        var boton = el("button", "boton-mini", "Reintentar"); boton.type = "button"; boton.dataset.codigo = o.codigo; acciones.appendChild(boton);
      }
      fila.appendChild(acciones);
      cuerpo.appendChild(fila);
    });
  }

  function pintarEventos(eventos) {
    var lista = document.getElementById("lista-eventos");
    lista.replaceChildren();
    if (!eventos.length) { lista.appendChild(el("li", "vacio", "Aún no hay eventos.")); return; }
    eventos.forEach(function (e) {
      var item = el("li");
      var clase = MALOS.indexOf(e.tipo) >= 0 ? "tipo malo" : (AVISOS.indexOf(e.tipo) >= 0 ? "tipo aviso" : "tipo");
      item.appendChild(el("span", clase, e.tipo.replace(/_/g, " ").toLowerCase()));
      item.appendChild(el("span", null, (e.orden_codigo ? e.orden_codigo + " · " : "") + e.detalle));
      item.appendChild(el("small", null, hora(e.creado_en)));
      lista.appendChild(item);
    });
  }

  function actualizar() {
    var estado = filtro.value ? "&estado=" + encodeURIComponent(filtro.value) : "";
    Promise.all([json("/api/resumen"), json("/api/ordenes?limite=12" + estado), json("/api/eventos?limite=30")])
      .then(function (r) { pintarResumen(r[0].cuerpo); pintarOrdenes(r[1].cuerpo); pintarEventos(r[2].cuerpo); })
      .catch(function () { /* la próxima actualización lo reintenta */ });
  }

  document.getElementById("form-orden").addEventListener("submit", function (evento) {
    evento.preventDefault();
    var form = evento.target;
    var mensaje = document.getElementById("mensaje-form");
    var datos = { cliente: form.cliente.value, direccion: form.direccion.value, servicio: form.servicio.value, prioridad: form.prioridad.value };
    json("/api/ordenes", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(datos) })
      .then(function (r) {
        if (r.ok) { mensaje.className = "mensaje ok"; mensaje.textContent = "Orden " + r.cuerpo.codigo + " creada y enviada al proveedor."; }
        else { mensaje.className = "mensaje error"; mensaje.textContent = (r.cuerpo.errores || []).map(function (e) { return e.campo + ": " + e.mensaje; }).join(" · ") || r.cuerpo.detail; }
        actualizar();
      });
  });

  document.getElementById("tabla-ordenes").addEventListener("click", function (evento) {
    var boton = evento.target.closest("button[data-codigo]");
    if (!boton) return;
    json("/api/ordenes/" + encodeURIComponent(boton.dataset.codigo) + "/reintentar", { method: "POST" }).then(actualizar);
  });

  filtro.addEventListener("change", actualizar);
  actualizar();
  setInterval(actualizar, 2000);
})();
