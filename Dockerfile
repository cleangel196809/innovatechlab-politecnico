# InnovaTech Lab · Campus PI — Odoo 17 Community para Render
FROM odoo:17.0

USER root
COPY ./addons /mnt/extra-addons
COPY ./deploy/start.sh /usr/local/bin/start.sh
RUN chmod +x /usr/local/bin/start.sh && chown -R odoo:odoo /mnt/extra-addons

USER odoo
ENV PGSSLMODE=require
EXPOSE 8069
ENTRYPOINT ["/usr/local/bin/start.sh"]
