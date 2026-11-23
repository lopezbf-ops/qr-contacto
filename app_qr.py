import streamlit as st
import qrcode
from qrcode.image.styledpil import StyledPilImage
from qrcode.image.styles.moduledrawers import RoundedModuleDrawer, SquareModuleDrawer
from qrcode.image.styles.colormasks import SolidFillColorMask
import qrcode.image.svg
from PIL import Image
import io
import urllib.parse
import urllib.request
from fpdf import FPDF
import tempfile
import os
import re
import base64
import zlib
import json
import uuid

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(
    page_title="Tarjeta Digital y Generador QR",
    page_icon="📱",
    layout="wide"
)

# --- DETECCIÓN AUTOMÁTICA DE LA URL DE LA APLICACIÓN ---
def obtener_url_base():
    """Detecta automáticamente la dirección web real donde está corriendo la app."""
    try:
        host = st.context.headers.get("Host", "")
        if host:
            protocolo = "http" if ("localhost" in host or "127.0.0.1" in host) else "https"
            return f"{protocolo}://{host}"
    except Exception:
        pass
    return ""

# --- ESTILOS CSS PERSONALIZADOS ---
st.markdown("""
    <style>
    .stApp {
        background-color: #FAF3E6;
    }
    h1, h2, h3 {
        color: #003153;
    }
    .stButton>button {
        background-color: #003153;
        color: #FAF3E6;
        border-radius: 6px;
        border: none;
    }
    .stButton>button:hover {
        background-color: #004777;
        color: #FFFFFF;
    }
    .tarjeta-digital {
        max-width: 440px;
        margin: 0 auto;
        background-color: #FFFFFF;
        border: 2px solid #003153;
        border-radius: 14px;
        padding: 28px 22px;
        text-align: center;
        box-shadow: 0 6px 18px rgba(0, 49, 83, 0.12);
    }
    .btn-accion {
        display: block;
        width: 100%;
        padding: 13px 16px;
        margin: 10px 0;
        background-color: #003153;
        color: #FAF3E6 !important;
        text-decoration: none;
        font-weight: 600;
        font-size: 16px;
        border-radius: 8px;
        text-align: center;
    }
    .btn-accion:hover {
        background-color: #004777;
    }
    </style>
""", unsafe_allow_html=True)

# --- FUNCIONES AUXILIARES DE IMAGEN Y SUBIDA ---
def normalizar_url_imagen(url):
    """Convierte enlaces de visualización de GitHub o Google Drive en enlaces directos."""
    url = url.strip()
    if "github.com" in url and "/blob/" in url:
        url = url.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
    match_drive = re.search(r"drive\.google\.com/file/d/([a-zA-Z0-9_-]+)", url)
    if match_drive:
        file_id = match_drive.group(1)
        url = f"https://lh3.googleusercontent.com/d/{file_id}"
    return url

def optimizar_raster(file_bytes, filename):
    """Redimensiona imágenes muy grandes a máx 1600px para carga rápida en móvil."""
    img = Image.open(io.BytesIO(file_bytes))
    max_dim = 1600
    if max(img.size) > max_dim:
        img.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

    out = io.BytesIO()
    ext = filename.lower().split(".")[-1]
    if ext == "png":
        img.save(out, format="PNG", optimize=True)
        return out.getvalue(), "tarjeta.png", "image/png"
    else:
        if img.mode in ("RGBA", "P"):
            img = img.convert("RGB")
        img.save(out, format="JPEG", quality=88, optimize=True)
        return out.getvalue(), "tarjeta.jpg", "image/jpeg"

def subir_a_catbox(file_bytes, filename, mime_type):
    """Sube archivo (JPG, PNG o SVG) mediante multipart/form-data y devuelve URL directa."""
    boundary = uuid.uuid4().hex
    crlf = b"\r\n"
    body = b"".join([
        b"--" + boundary.encode() + crlf,
        b'Content-Disposition: form-data; name="reqtype"' + crlf + crlf,
        b"fileupload" + crlf,
        b"--" + boundary.encode() + crlf,
        f'Content-Disposition: form-data; name="fileToUpload"; filename="{filename}"'.encode() + crlf,
        f"Content-Type: {mime_type}".encode() + crlf + crlf,
        file_bytes + crlf,
        b"--" + boundary.encode() + b"--" + crlf
    ])
    req = urllib.request.Request(
        "https://catbox.moe/user/api.php",
        data=body,
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "Mozilla/5.0"
        }
    )
    with urllib.request.urlopen(req, timeout=20) as resp:
        res_text = resp.read().decode("utf-8").strip()
        if res_text.startswith("http"):
            return res_text
    raise ValueError("No se obtuvo URL válida del servidor de alojamiento.")

def subir_imagen_automatica(uploaded_file):
    """Gestiona la optimización y subida automática de JPG, PNG o SVG."""
    raw_bytes = uploaded_file.getvalue()
    fname = uploaded_file.name
    is_svg = fname.lower().endswith(".svg")

    if is_svg:
        comprimido = zlib.compress(raw_bytes, level=9)
        b64_zlib = base64.urlsafe_b64encode(comprimido).decode("ascii")
        if len(b64_zlib) <= 1750:
            return {"tipo": "svg_inline", "data": b64_zlib}
        url_remota = subir_a_catbox(raw_bytes, "tarjeta.svg", "image/svg+xml")
        return {"tipo": "url", "data": url_remota}

    opt_bytes, opt_name, mime = optimizar_raster(raw_bytes, fname)
    try:
        b64_img = base64.b64encode(opt_bytes).decode("ascii")
        post_data = urllib.parse.urlencode({
            "key": "6d207e02198a847aa98d0a2a901485a5",
            "action": "upload",
            "source": b64_img,
            "format": "json"
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://freeimage.host/api/1/upload",
            data=post_data,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            resultado = json.loads(resp.read().decode("utf-8"))
            if resultado.get("status_code") == 200:
                return {"tipo": "url", "data": resultado["image"]["url"]}
    except Exception:
        pass

    url_remota = subir_a_catbox(opt_bytes, opt_name, mime)
    return {"tipo": "url", "data": url_remota}

# ==============================================================================
# VISTA 1: TARJETA DIGITAL INTERACTIVA (AL ESCANEAR QR INTERACTIVO)
# ==============================================================================
params = st.query_params
if params.get("vista") == "tarjeta":
    t_nombre = params.get("n", "Fernando")
    t_apellidos = params.get("a", "López Barrera")
    t_titulo = params.get("t", "Nutriólogo")
    t_empresa = params.get("e", "Instituto de Neurobiología, UNAM")
    t_tel = params.get("tel", "+524422381028")
    t_correo = params.get("mail", "lopezbfe@unam.mx")
    t_web = params.get("web", "https://www.inb.unam.mx")
    t_dir = params.get("dir", "Campus Juriquilla, Blvd. Juriquilla 3001, Querétaro, Qro., 76230, México")

    uri_tel = f"tel:{t_tel}"
    uri_mail = f"mailto:{t_correo}?subject={urllib.parse.quote('Contacto desde Tarjeta Digital')}"
    uri_web = t_web if t_web.startswith("http") else f"https://{t_web}"
    uri_map = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(t_dir)}"

    btn_tel_html = f'<a class="btn-accion" href="{uri_tel}">📞 Llamar ({t_tel})</a>' if len(t_tel) > 3 else ""
    btn_mail_html = f'<a class="btn-accion" href="{uri_mail}">✉️ Enviar Correo ({t_correo})</a>' if t_correo else ""
    btn_web_html = f'<a class="btn-accion" href="{uri_web}" target="_blank">🌐 Visitar Sitio Web</a>' if t_web else ""
    btn_map_html = f'<a class="btn-accion" href="{uri_map}" target="_blank">📍 Abrir Ubicación en Mapa</a>' if t_dir else ""

    vcf_data = (
        f"BEGIN:VCARD\n"
        f"VERSION:3.0\n"
        f"N;CHARSET=UTF-8:{t_apellidos};{t_nombre};;;\n"
        f"FN;CHARSET=UTF-8:{t_nombre} {t_apellidos}\n"
        f"ORG;CHARSET=UTF-8:{t_empresa}\n"
        f"TITLE;CHARSET=UTF-8:{t_titulo}\n"
        f"TEL;TYPE=WORK,VOICE:{t_tel}\n"
        f"EMAIL;TYPE=WORK,INTERNET:{t_correo}\n"
        f"URL:{uri_web}\n"
        f"ADR;TYPE=WORK;CHARSET=UTF-8:;;{t_dir};;;;\n"
        f"END:VCARD"
    )

    st.markdown(f"""
        <div class="tarjeta-digital">
            <h2 style="margin-bottom: 4px; color: #003153;">{t_nombre} {t_apellidos}</h2>
            <p style="margin: 0; font-weight: 600; color: #335C7A; font-size: 16px;">{t_titulo}</p>
            <p style="margin: 4px 0 18px 0; color: #555555; font-size: 14px;">{t_empresa}</p>
            <hr style="border: 0; border-top: 1px solid #D9CFC1; margin-bottom: 18px;">
            {btn_tel_html}
            {btn_mail_html}
            {btn_web_html}
            {btn_map_html}
        </div>
    """, unsafe_allow_html=True)

    st.markdown("<br>", unsafe_allow_html=True)
    col_c1, col_c2, col_c3 = st.columns([1, 2, 1])
    with col_c2:
        st.download_button(
            label="📇 Guardar Contacto en Agenda (.vcf)",
            data=vcf_data.encode("utf-8"),
            file_name=f"{t_nombre}_{t_apellidos}.vcf",
            mime="text/vcard",
            use_container_width=True
        )
    st.stop()

# ==============================================================================
# VISTA 2A: VISOR DE TARJETA EN IMAGEN (JPG / PNG / SVG REMOTO)
# ==============================================================================
if params.get("vista") == "imagen":
    img_url_raw = params.get("img", "")
    img_titulo = params.get("titulo", "")
    img_url = normalizar_url_imagen(img_url_raw)

    col_i1, col_i2, col_i3 = st.columns([1, 2, 1])
    with col_i2:
        if img_titulo:
            st.markdown(f"<h3 style='text-align:center; color:#003153;'>{img_titulo}</h3>", unsafe_allow_html=True)

        if img_url:
            if img_url.lower().endswith(".svg"):
                st.markdown(
                    f'<div style="text-align:center;"><img src="{img_url}" style="width:100%; border-radius:10px; box-shadow:0 4px 14px rgba(0,0,0,0.15);" /></div>',
                    unsafe_allow_html=True
                )
            else:
                st.image(img_url, use_container_width=True)

            try:
                req = urllib.request.Request(img_url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as resp:
                    img_bytes = resp.read()
                lower_u = img_url.lower()
                if ".svg" in lower_u:
                    ext, mime = "svg", "image/svg+xml"
                elif ".png" in lower_u:
                    ext, mime = "png", "image/png"
                else:
                    ext, mime = "jpg", "image/jpeg"

                st.download_button(
                    label="⬇️ Guardar Tarjeta en el Teléfono",
                    data=img_bytes,
                    file_name=f"Tarjeta_Presentacion.{ext}",
                    mime=mime,
                    use_container_width=True
                )
            except Exception:
                st.caption("Mantén presionada la imagen para guardarla en tu teléfono.")
        else:
            st.warning("No se recibió ninguna dirección de imagen válida.")
    st.stop()

# ==============================================================================
# VISTA 2B: VISOR DE TARJETA VECTORIAL SVG INCRUSTADA EN EL QR
# ==============================================================================
if params.get("vista") == "svg":
    d_param = params.get("d", "")
    img_titulo = params.get("titulo", "")
    col_s1, col_s2, col_s3 = st.columns([1, 2, 1])
    with col_s2:
        if img_titulo:
            st.markdown(f"<h3 style='text-align:center; color:#003153;'>{img_titulo}</h3>", unsafe_allow_html=True)
        try:
            svg_bytes = zlib.decompress(base64.urlsafe_b64decode(d_param.encode("ascii")))
            b64_render = base64.b64encode(svg_bytes).decode("ascii")
            st.markdown(
                f'<div style="text-align:center;"><img src="data:image/svg+xml;base64,{b64_render}" style="width:100%; border-radius:10px; box-shadow:0 4px 14px rgba(0,0,0,0.15);" /></div>',
                unsafe_allow_html=True
            )
            st.markdown("<br>", unsafe_allow_html=True)
            st.download_button(
                label="⬇️ Descargar Tarjeta Vectorial (.svg)",
                data=svg_bytes,
                file_name="Tarjeta_Presentacion.svg",
                mime="image/svg+xml",
                use_container_width=True
            )
        except Exception:
            st.error("No se pudo decodificar el archivo SVG.")
    st.stop()

# ==============================================================================
# FUNCIONES DE GENERACIÓN DE QR Y PDF (MODO GENERADOR)
# ==============================================================================
def hex_to_rgb(hex_color):
    hex_color = hex_color.lstrip('#')
    return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))

def generar_qr_png(datos, color_frente="#003153", color_fondo="#FAF3E6", logo_file=None, redondeado=False):
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=14,
        border=2,
    )
    qr.add_data(datos)
    qr.make(fit=True)

    rgb_frente = hex_to_rgb(color_frente)
    rgb_fondo = hex_to_rgb(color_fondo)

    drawer = RoundedModuleDrawer() if redondeado else SquareModuleDrawer()

    img = qr.make_image(
        image_factory=StyledPilImage,
        module_drawer=drawer,
        color_mask=SolidFillColorMask(back_color=rgb_fondo, front_color=rgb_frente)
    ).convert("RGBA")

    if logo_file is not None:
        logo_file.seek(0)
        logo = Image.open(logo_file).convert("RGBA")
        qr_width, qr_height = img.size
        logo_max_size = int(qr_width * 0.24)
        logo.thumbnail((logo_max_size, logo_max_size), Image.Resampling.LANCZOS)

        pad = 8
        bg_size = (logo.size[0] + pad * 2, logo.size[1] + pad * 2)
        logo_bg = Image.new("RGBA", bg_size, rgb_fondo + (255,))

        pos_bg = ((qr_width - bg_size[0]) // 2, (qr_height - bg_size[1]) // 2)
        pos_logo = ((qr_width - logo.size[0]) // 2, (qr_height - logo.size[1]) // 2)

        img.paste(logo_bg, pos_bg, logo_bg)
        img.paste(logo, pos_logo, logo)

    buf = io.BytesIO()
    img.save(buf, format="PNG", dpi=(300, 300))
    buf.seek(0)
    return buf, img

def generar_qr_svg(datos):
    factory = qrcode.image.svg.SvgPathImage
    img = qrcode.make(
        datos,
        image_factory=factory,
        error_correction=qrcode.constants.ERROR_CORRECT_H,
        box_size=10,
        border=2
    )
    buf = io.BytesIO()
    img.save(buf)
    buf.seek(0)
    return buf

def generar_pdf_individual(png_buf, enlace_clicable=None, titulo_pie=""):
    pdf = FPDF(orientation="P", unit="mm", format=(60, 65))
    pdf.set_auto_page_break(False)
    pdf.add_page()

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
        tmp.write(png_buf.getvalue())
        tmp_path = tmp.name

    if enlace_clicable:
        pdf.image(tmp_path, x=5, y=4, w=50, h=50, link=enlace_clicable)
    else:
        pdf.image(tmp_path, x=5, y=4, w=50, h=50)

    os.remove(tmp_path)

    if titulo_pie:
        pdf.set_font("Helvetica", "B", 8)
        pdf.set_text_color(0, 49, 83)
        pdf.set_xy(5, 56)
        pdf.cell(50, 5, titulo_pie, align="C")

    return bytes(pdf.output())

def limpiar_texto_latin1(texto):
    return texto.encode("latin-1", "replace").decode("latin-1")

def generar_pdf_doble_cara(png_vcard, png_interactivo, url_interactiva, nombre_completo, subtitulo, color_fondo_hex):
    pdf = FPDF(orientation="L", unit="mm", format=(50, 90))
    pdf.set_auto_page_break(False)

    r, g, b = hex_to_rgb(color_fondo_hex)
    t_r, t_g, t_b = (255, 255, 255) if (r * 0.299 + g * 0.587 + b * 0.114) < 128 else (0, 49, 83)

    pdf.add_page()
    pdf.set_fill_color(r, g, b)
    pdf.rect(0, 0, 90, 50, style="F")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp1:
        tmp1.write(png_vcard.getvalue())
        tmp1_path = tmp1.name

    pdf.image(tmp1_path, x=8, y=9, w=32, h=32)
    os.remove(tmp1_path)

    pdf.set_text_color(t_r, t_g, t_b)
    pdf.set_font("Helvetica", "B", 10.5)
    pdf.set_xy(43, 15)
    pdf.multi_cell(41, 5, limpiar_texto_latin1(nombre_completo), align="L")

    pdf.set_font("Helvetica", "", 7.5)
    pdf.set_xy(43, 27)
    pdf.multi_cell(41, 4, limpiar_texto_latin1(subtitulo), align="L")

    pdf.set_font("Helvetica", "B", 6)
    pdf.set_xy(8, 42)
    pdf.cell(32, 4, "GUARDAR CONTACTO", align="C")

    pdf.add_page()
    pdf.set_fill_color(r, g, b)
    pdf.rect(0, 0, 90, 50, style="F")

    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp2:
        tmp2.write(png_interactivo.getvalue())
        tmp2_path = tmp2.name

    pdf.image(tmp2_path, x=28, y=6, w=34, h=34, link=url_interactiva)
    os.remove(tmp2_path)

    pdf.set_text_color(t_r, t_g, t_b)
    pdf.set_font("Helvetica", "B", 6.5)
    pdf.set_xy(10, 41.5)
    pdf.cell(70, 4, "ESCANEA PARA LLAMAR, CORREO, WEB Y MAPA", align="C", link=url_interactiva)

    return bytes(pdf.output())

def generar_pdf_4qr(qrs_dict, uris_dict, color_fondo_hex):
    pdf = FPDF(orientation="L", unit="mm", format=(50, 90))
    pdf.set_auto_page_break(False)
    pdf.add_page()

    r, g, b = hex_to_rgb(color_fondo_hex)
    pdf.set_fill_color(r, g, b)
    pdf.rect(0, 0, 90, 50, style="F")

    qr_size = 17.5
    gap = 3.5
    start_x = (90 - (4 * qr_size + 3 * gap)) / 2
    y_pos = 13.5

    etiquetas = ["LLAMAR", "CORREO", "WEB", "UBICACION"]
    claves = ["tel", "email", "web", "map"]

    pdf.set_font("Helvetica", "B", 6.5)
    t_r, t_g, t_b = (255, 255, 255) if (r * 0.299 + g * 0.587 + b * 0.114) < 128 else (0, 49, 83)
    pdf.set_text_color(t_r, t_g, t_b)

    for idx, clave in enumerate(claves):
        if clave in qrs_dict:
            x = start_x + idx * (qr_size + gap)
            with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                tmp.write(qrs_dict[clave].getvalue())
                tmp_path = tmp.name

            pdf.image(tmp_path, x=x, y=y_pos, w=qr_size, h=qr_size, link=uris_dict.get(clave, ""))
            os.remove(tmp_path)

            pdf.set_xy(x, y_pos + qr_size + 1.5)
            pdf.cell(qr_size, 4, etiquetas[idx], align="C", link=uris_dict.get(clave, ""))

    return bytes(pdf.output())

# --- BARRA LATERAL: ESTILO Y LOGO ---
url_detectada = obtener_url_base()

with st.sidebar:
    st.header("🎨 Estilo Visual")
    color_frente = st.color_picker("Color del código QR", "#003153")
    color_fondo = st.color_picker("Color de fondo", "#FAF3E6")
    estilo_redondo = st.checkbox("Módulos redondeados", value=False)

    st.markdown("---")
    st.subheader("🖼️ Logotipo Central (Opcional)")
    logo_subido = st.file_uploader("Sube isotipo TONAL o escudo (PNG/JPG)", type=["png", "jpg", "jpeg"])
    if logo_subido:
        st.image(logo_subido, width=90, caption="Logo activo")

    st.markdown("---")
    st.subheader("🌐 Dirección Web Detectada")
    url_app_publica = st.text_input(
        "URL base de esta aplicación:",
        value=url_detectada,
        help="Se detecta automáticamente al abrir la página en Streamlit."
    )

# --- ENCABEZADO PRINCIPAL ---
st.title("Generador Multipropósito de Códigos QR")
st.markdown("Crea códigos para tarjetas de presentación (vCard, Tarjeta Digital, Imagen y Enlaces Directos) y etiquetas de laboratorio.")

# --- PESTAÑAS DE MODOS ---
tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "📇 1. Contacto (vCard + Digital + 4 Enlaces)",
    "🖼️ 2. Tarjeta en Imagen",
    "🧪 3. Reactivos / Lotes / Texto",
    "📶 4. Acceso Wi-Fi",
    "💬 5. WhatsApp y 📅 Evento"
])

# ==============================================================================
# PESTAÑA 1: CONTACTO (vCard + QR INTERACTIVO + 4 QR INDIVIDUALES)
# ==============================================================================
with tab1:
    st.subheader("Datos del Contacto")

    col1, col2 = st.columns(2)
    with col1:
        nombre = st.text_input("Nombre(s)", value="Fernando")
        apellidos = st.text_input("Apellidos", value="López Barrera")
        titulo = st.text_input("Puesto / Título / Marca", value="Nutriólogo")
        empresa = st.text_input("Institución / Organización", value="Instituto de Neurobiología, UNAM")
    with col2:
        telefono = st.text_input("Teléfono (10 dígitos o con +52)", value="4422381028")
        correo = st.text_input("Correo electrónico", value="lopezbfe@unam.mx")
        web = st.text_input("Sitio Web / Portafolio", value="https://www.inb.unam.mx")

    st.markdown("**Dirección física:**")
    cd1, cd2, cd3, cd4 = st.columns([2, 1, 1, 1])
    with cd1:
        calle = st.text_input("Calle y número", value="Campus Juriquilla, Blvd. Juriquilla 3001")
    with cd2:
        ciudad = st.text_input("Ciudad / Localidad", value="Querétaro")
    with cd3:
        estado = st.text_input("Estado", value="Qro.")
    with cd4:
        cp = st.text_input("C.P.", value="76230")

    if st.button("Generar Todos los Códigos de Contacto", key="btn_contacto"):
        st.markdown("---")

        tel_digits = "".join(c for c in telefono if c.isdigit())
        if len(tel_digits) == 10:
            tel_clean = f"+52{tel_digits}"
        elif telefono.strip().startswith("+"):
            tel_clean = "+" + tel_digits
        else:
            tel_clean = f"+{tel_digits}"

        uri_web = web.strip() if web.strip().startswith("http") else f"https://{web.strip()}"
        direccion_completa = f"{calle.strip()}, {ciudad.strip()}, {estado.strip()}, {cp.strip()}, México"

        vcard_lines = [
            "BEGIN:VCARD",
            "VERSION:3.0",
            f"N;CHARSET=UTF-8:{apellidos.strip()};{nombre.strip()};;;",
            f"FN;CHARSET=UTF-8:{nombre.strip()} {apellidos.strip()}",
            f"ORG;CHARSET=UTF-8:{empresa.strip()}",
            f"TITLE;CHARSET=UTF-8:{titulo.strip()}",
            f"TEL;TYPE=WORK,VOICE:{tel_clean}",
            f"EMAIL;TYPE=WORK,INTERNET:{correo.strip()}",
            f"URL:{uri_web}",
            f"ADR;TYPE=WORK;CHARSET=UTF-8:;;{calle.strip()};{ciudad.strip()};{estado.strip()};{cp.strip()};México",
            "END:VCARD"
        ]
        vcard_str = "\n".join(vcard_lines)

        base_clean = url_app_publica.strip().rstrip("/")
        query_params = urllib.parse.urlencode({
            "vista": "tarjeta",
            "n": nombre.strip(),
            "a": apellidos.strip(),
            "t": titulo.strip(),
            "e": empresa.strip(),
            "tel": tel_clean,
            "mail": correo.strip(),
            "web": uri_web,
            "dir": direccion_completa
        })
        url_tarjeta_interactiva = f"{base_clean}/?{query_params}"

        uri_tel = f"tel:{tel_clean}"
        uri_email = f"mailto:{correo.strip()}?subject={urllib.parse.quote('Contacto desde tarjeta QR')}"
        uri_map = f"https://www.google.com/maps/search/?api=1&query={urllib.parse.quote(direccion_completa)}"

        col_vc, col_int = st.columns(2)

        with col_vc:
            st.markdown("### A. QR vCard (Guardar en Agenda - Offline)")
            png_vcard, _ = generar_qr_png(vcard_str, color_frente, color_fondo, logo_subido, estilo_redondo)
            svg_vcard = generar_qr_svg(vcard_str)
            pdf_vcard = generar_pdf_individual(png_vcard, titulo_pie=f"{nombre} {apellidos}")

            st.image(png_vcard, width=210)
            st.caption("Ideal para el **frente** de tu tarjeta: funciona sin internet y abre la agenda del teléfono.")
            bv1, bv2, bv3 = st.columns(3)
            with bv1:
                st.download_button("⬇️ PNG", png_vcard, file_name="QR_vCard.png", mime="image/png", key="vc_png")
            with bv2:
                st.download_button("⬇️ PDF", pdf_vcard, file_name="QR_vCard.pdf", mime="application/pdf", key="vc_pdf")
            with bv3:
                st.download_button("⬇️ SVG", svg_vcard, file_name="QR_vCard.svg", mime="image/svg+xml", key="vc_svg")

        with col_int:
            st.markdown("### B. QR Interactivo (Botones de Acción - Online)")
            png_inter, _ = generar_qr_png(url_tarjeta_interactiva, color_frente, color_fondo, logo_subido, estilo_redondo)
            svg_inter = generar_qr_svg(url_tarjeta_interactiva)
            pdf_inter = generar_pdf_individual(png_inter, enlace_clicable=url_tarjeta_interactiva, titulo_pie="TARJETA DIGITAL")

            st.image(png_inter, width=210)
            st.caption("Ideal para el **reverso** de tu tarjeta: abre una pantalla con botones directos para Llamar, Correo, Web y Mapa.")
            bi1, bi2, bi3 = st.columns(3)
            with bi1:
                st.download_button("⬇️ PNG", png_inter, file_name="QR_Tarjeta_Digital.png", mime="image/png", key="in_png")
            with bi2:
                st.download_button("⬇️ PDF", pdf_inter, file_name="QR_Tarjeta_Digital.pdf", mime="application/pdf", key="in_pdf")
            with bi3:
                st.download_button("⬇️ SVG", svg_inter, file_name="QR_Tarjeta_Digital.svg", mime="image/svg+xml", key="in_svg")
            st.markdown(f"[🔗 Probar vista de Tarjeta Digital en navegador]({url_tarjeta_interactiva})")

        st.markdown("---")
        st.markdown("### C. Cuatro Códigos Individuales")

        items_indiv = [
            ("tel", "📞 Llamada Directa", uri_tel, "QR_Llamada", "LLAMAR"),
            ("email", "✉️ Enviar Correo", uri_email, "QR_Correo", "CORREO"),
            ("web", "🌐 Abrir Sitio Web", uri_web, "QR_Web", "SITIO WEB"),
            ("map", "📍 Ubicación Mapa", uri_map, "QR_Mapa", "UBICACION"),
        ]

        cols_4 = st.columns(4)
        qrs_para_pdf = {}
        uris_para_pdf = {}

        for i, (clave, titulo_card, uri, fname, etiqueta
