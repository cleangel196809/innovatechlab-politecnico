# InnovaTech Lab · Campus PI — Odoo 17 Community para Render
FROM odoo:17.0

USER root
# Voz neuronal (edge-tts), PowerPoint/Word institucionales y lectura de Excel para cargar usuarios
RUN pip3 install --no-cache-dir "edge-tts==7.0.2" "python-pptx==1.0.2" "python-docx==1.1.2" "openpyxl>=3.0" \
    || pip3 install --no-cache-dir --break-system-packages "edge-tts==7.0.2" "python-pptx==1.0.2" "python-docx==1.1.2" "openpyxl>=3.0"
COPY ./addons /mnt/extra-addons
COPY ./deploy/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh && chown -R odoo:odoo /mnt/extra-addons

USER odoo
ENV PGSSLMODE=require
EXPOSE 8069
ENTRYPOINT ["/usr/local/bin/start.sh"]
