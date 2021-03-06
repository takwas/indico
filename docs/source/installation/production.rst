Installation guide (production)
===============================

We provide guides to install Indico on CentOS and Debian systems.
While other distributions are not officially supported, they should
work fine, but the installation steps (especially package names) may
need some slight adjustments.

Our guide covers a single-machine installation where Indico, Celery,
Redis and PostgreSQL run on the same machine.  This should be fine for
almost all Indico instances, but adapting the steps to multiple machines
is not particularly hard either.


CentOS7 / CC7
-------------

Except for minor differences, this guide applies to both vanilla CentOS7
and the CERN flavor of CentOS, CC7 (CentOS CERN 7).


.. _centos-epel:

1. Enable EPEL
^^^^^^^^^^^^^^

.. code-block:: shell

    yum install -y epel-release

.. note::

    If you use CC7, EPEL is already enabled and this step is not necessary


.. _centos-pkg:

2. Install Packages
^^^^^^^^^^^^^^^^^^^

Edit ``/etc/yum.repos.d/CentOS-Base.repo`` and add ``exclude=postgresql*``
to the ``[base]`` and ``[updates]`` sections, as described in the
`PostgreSQL wiki`_.

.. code-block:: shell

    yum install -y https://download.postgresql.org/pub/repos/yum/9.6/redhat/rhel-7-x86_64/pgdg-centos96-9.6-3.noarch.rpm
    yum install -y postgresql96 postgresql96-server postgresql96-libs postgresql96-devel postgresql96-contrib
    yum install -y gcc redis nginx uwsgi uwsgi-plugin-python
    yum install -y python-devel python-virtualenv libjpeg-turbo-devel libxslt-devel libxml2-devel libffi-devel pcre-devel libyaml-devel
    /usr/pgsql-9.6/bin/postgresql96-setup initdb
    systemctl start postgresql-9.6.service redis.service


.. _centos-db:

3. Create a Database
^^^^^^^^^^^^^^^^^^^^

We create a user and database for indico and enable the necessary
Postgres extensions (which can only be done by the Postgres superuser)

.. code-block:: shell

    su - postgres -c 'createuser indico'
    su - postgres -c 'createdb -O indico indico'
    su - postgres -c 'psql indico -c "CREATE EXTENSION unaccent; CREATE EXTENSION pg_trgm;"'

.. warning::

    Do not forget to setup a cronjob that creates regular database
    backups once you start using Indico in production!


.. _centos-web:

4. Configure uWSGI & nginx
^^^^^^^^^^^^^^^^^^^^^^^^^^

The default uWSGI and nginx configuration files should work fine in
most cases.

.. code-block:: shell

    cat > /etc/uwsgi.ini <<'EOF'
    [uwsgi]
    uid = indico
    gid = nginx
    pidfile = /run/uwsgi/uwsgi.pid

    processes = 4
    enable-threads = false
    chmod-socket = 770
    socket = /opt/indico/web/uwsgi.sock
    stats = /opt/indico/web/uwsgi-stats.sock
    protocol = uwsgi

    master = true
    auto-procname = true
    procname-prefix-spaced = indico
    disable-logging = true

    plugin = python
    single-interpreter = true

    touch-reload = /opt/indico/web/indico.wsgi
    wsgi-file = /opt/indico/web/indico.wsgi
    virtualenv = /opt/indico/.venv

    vacuum = true
    buffer-size = 20480
    memory-report = true
    max-requests = 2500
    harakiri = 900
    harakiri-verbose = true
    reload-on-rss = 2048
    evil-reload-on-rss = 8192
    EOF


.. note::

    Replace ``YOURHOSTNAME`` in the next file with the hostname on which
    your Indico instance should be available, e.g. ``indico.yourdomain.com``


.. code-block:: shell

    cat > /etc/nginx/conf.d/indico.conf <<'EOF'
    server {
      listen 80;
      listen [::]:80;
      server_name YOURHOSTNAME;
      return 301 https://$server_name$request_uri;
    }

    server {
      listen       *:443 ssl http2;
      listen       [::]:443 ssl http2 default ipv6only=on;
      server_name  YOURHOSTNAME;

      ssl on;

      ssl_certificate           /etc/ssl/nginx/indico.crt;
      ssl_certificate_key       /etc/ssl/nginx/indico.key;
      ssl_session_cache         shared:SSL:10m;
      ssl_session_timeout       5m;
      ssl_protocols             TLSv1 TLSv1.1 TLSv1.2;
      ssl_ciphers               ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA:ECDHE-ECDSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA:ECDHE-RSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:DHE-RSA-AES256-SHA256:DHE-RSA-AES256-SHA:ECDHE-ECDSA-DES-CBC3-SHA:ECDHE-RSA-DES-CBC3-SHA:EDH-RSA-DES-CBC3-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA256:AES128-SHA:AES256-SHA:DES-CBC3-SHA:!DSS;
      ssl_prefer_server_ciphers on;

      access_log            /opt/indico/log/nginx/access.log combined;
      error_log             /opt/indico/log/nginx/error.log;

      location /.xsf/indico/ {
        internal;
        alias /opt/indico/;
      }

      location ~ ^/static/assets/(core|(?:plugin|theme)-[^/]+)/(.*)$ {
        alias /opt/indico/assets/$1/$2;
        access_log off;
      }

      location ~ ^/(ihelp|css|images|js|static(?!/plugins|/assets|/themes|/custom))(/.*)$ {
        alias /opt/indico/web/htdocs/$1$2;
        access_log off;
      }

      location /robots.txt {
        alias /opt/indico/web/htdocs/robots.txt;
        access_log off;
      }

      location / {
        root /var/empty/nginx;
        include /etc/nginx/uwsgi_params;
        uwsgi_pass unix:/opt/indico/web/uwsgi.sock;
        uwsgi_param UWSGI_SCHEME $scheme;
        uwsgi_read_timeout 15m;
        uwsgi_buffers 32 32k;
        uwsgi_busy_buffers_size 128k;
        uwsgi_hide_header X-Sendfile;
        client_max_body_size 1G;
      }
    }
    EOF


.. _centos-ssl:

5. Create an SSL Certificate
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

First, create the folders for the certificate/key and set restrictive
permissions on them:

.. code-block:: shell

    mkdir /etc/ssl/nginx
    chown root:root /etc/ssl/nginx/
    chmod 700 /etc/ssl/nginx

If you are just trying out Indico you can simply use a self-signed
certificate (your browser will show a warning which you will have
to confirm when accessing your Indico instance for the first time).


.. note::

    Do not forget to replace ``YOURHOSTNAME`` with the same value
    you used above

.. code-block:: shell

    openssl req -x509 -nodes -newkey rsa:4096 -subj /CN=YOURHOSTNAME -keyout /etc/ssl/nginx/indico.key -out /etc/ssl/nginx/indico.crt


While a self-signed certificate works for testing, it is not suitable
for a production system.  You can either buy a certificate from any
commercial certification authority or get a free one from
`Let's Encrypt`_. Once you have a proper key/certificate, save them
as ``/etc/ssl/nginx/indico.key`` and ``/etc/ssl/nginx/indico.crt``.


.. _centos-selinux:

6. Configure SELinux
^^^^^^^^^^^^^^^^^^^^

Indico works fine with SELinux enabled, but you need to load a custom
SELinux module to tell SELinux about Indico's files and how they
should be handled.

.. code-block:: shell

    cat > /tmp/indico.cil <<'EOF'
    ; define custom type that logrotate can access
    (type indico_log_t)
    (typeattributeset file_type (indico_log_t))
    (typeattributeset logfile (indico_log_t))
    (roletype object_r indico_log_t)

    ; allow logrotate to reload systemd services
    (allow logrotate_t init_t (service (start)))
    (allow logrotate_t policykit_t (dbus (send_msg)))
    (allow policykit_t logrotate_t (dbus (send_msg)))

    ; make sure the uwsgi socket is writable by the webserver
    (typetransition unconfined_service_t usr_t sock_file "uwsgi.sock" httpd_sys_rw_content_t)
    (filecon "/opt/indico/web/uwsgi\.sock" socket (system_u object_r httpd_sys_rw_content_t ((s0)(s0))))

    ; set proper types for our log dirs
    (filecon "/opt/indico/log(/.*)?" any (system_u object_r indico_log_t ((s0)(s0))))
    (filecon "/opt/indico/log/nginx(/.*)?" any (system_u object_r httpd_log_t ((s0)(s0))))
    EOF
    semodule -i /tmp/indico.cil


.. _centos-install:

7. Install Indico
^^^^^^^^^^^^^^^^^

Celery runs as a background daemon. Add a systemd unit file for it:

.. code-block:: shell

    cat > /etc/systemd/system/indico-celery.service <<'EOF'
    [Unit]
    Description=Indico Celery
    After=network.target

    [Service]
    ExecStart=/opt/indico/.venv/bin/indico celery worker -B
    Restart=always
    SyslogIdentifier=indico-celery
    User=indico
    Group=nginx
    Type=simple

    [Install]
    WantedBy=multi-user.target
    EOF
    systemctl daemon-reload


Now create a user that will be used to run Indico and switch to it:

.. code-block:: shell

    useradd -rm -g nginx -d /opt/indico -s /bin/bash indico
    su - indico


You are now ready to install Indico:

.. code-block:: shell

    virtualenv ~/.venv
    source ~/.venv/bin/activate
    pip install -U pip setuptools
    pip install indico

.. note::

    If you use a custom-built indico wheel, use ``pip install /path/to/indico-*.whl``
    instead of ``pip install indico``


.. _centos-config:

8. Configure Indico
^^^^^^^^^^^^^^^^^^^

Once Indico is installed, you can run the configuration wizard.  You can
keep the defaults for most options, but make sure to use ``https://YOURHOSTNAME``
when prompted for the Indico URL. Also specify valid email addresses when asked
and enter a valid SMTP server Indico can use to send emails.  When asked for the
default timezone make sure this is the main time zone used in your Indico instance.

.. code-block:: shell

    indico setup wizard


Now finish setting up the directory structure and permissions:

.. code-block:: shell

    mkdir ~/log/nginx
    chmod go-rwx ~/* ~/.*
    chmod 710 ~/ ~/archive ~/assets ~/cache ~/log ~/tmp
    chmod 750 ~/web ~/.venv
    chmod g+w ~/log/nginx
    restorecon -R ~/
    echo -e "\nStaticFileMethod = ('xaccelredirect', {'/opt/indico': '/.xsf/indico'})" >> ~/etc/indico.conf


9. Create database schema
^^^^^^^^^^^^^^^^^^^^^^^^^

Finally you can create the database schema and switch back to *root*:

.. code-block:: shell

    indico db prepare
    exit


.. _centos-launch:

10. Launch Indico
^^^^^^^^^^^^^^^^^

You can now start Indico and set it up to start automatically when the
server is rebooted:

.. code-block:: shell

    systemctl restart uwsgi.service nginx.service indico-celery.service
    systemctl enable uwsgi.service nginx.service postgresql-9.6.service redis.service indico-celery.service


.. _centos-firewall:

11. Open the Firewall
^^^^^^^^^^^^^^^^^^^^^

.. code-block:: shell

    firewall-cmd --permanent --add-port 443/tcp --add-port 80/tcp
    firewall-cmd --reload

.. note::

    This is only needed if you use CC7 as CentOS7 has no firewall enabled
    by default


.. _centos-user:

12. Create an Indico user
^^^^^^^^^^^^^^^^^^^^^^^^^

Access ``https://YOURHOSTNAME`` in your browser and follow the steps
displayed there to create your initial user.



Debian / Ubuntu
---------------

Except for minor differences, this guide applies to both Debian and Ubuntu.


.. _deb-pkg:

1. Install Packages
^^^^^^^^^^^^^^^^^^^

PostgreSQL and nginx are installed from their upstream repos to get
much more recent versions.

.. code-block:: shell

    echo "deb http://apt.postgresql.org/pub/repos/apt/ $(lsb_release -cs)-pgdg main" > /etc/apt/sources.list.d/pgdg.list
    echo "deb http://nginx.org/packages/$(lsb_release -is | tr '[:upper:]' '[:lower:]')/ $(lsb_release -cs) nginx" > /etc/apt/sources.list.d/nginx.list
    wget --quiet -O - https://www.postgresql.org/media/keys/ACCC4CF8.asc | apt-key add -
    wget --quiet -O - https://nginx.org/keys/nginx_signing.key | apt-key add -
    apt update
    apt install -y postgresql-9.6 libpq-dev nginx python-dev python-virtualenv libxslt1-dev libxml2-dev libffi-dev libpcre3-dev libyaml-dev build-essential redis-server uwsgi uwsgi-plugin-python


If you use Debian, run this command:

.. code-block:: shell

    apt install -y libjpeg62-turbo-dev


If you use Ubuntu, run this instead:

.. code-block:: shell

    apt install -y libjpeg-turbo8-dev zlib1g-dev


.. _deb-db:

2. Create a Database
^^^^^^^^^^^^^^^^^^^^

We create a user and database for indico and enable the necessary
Postgres extensions (which can only be done by the Postgres superuser)

.. code-block:: shell

    su - postgres -c 'createuser indico'
    su - postgres -c 'createdb -O indico indico'
    su - postgres -c 'psql indico -c "CREATE EXTENSION unaccent; CREATE EXTENSION pg_trgm;"'

.. warning::

    Do not forget to setup a cronjob that creates regular database
    backups once you start using Indico in production!


.. _deb-web:

3. Configure uWSGI & nginx
^^^^^^^^^^^^^^^^^^^^^^^^^^

The default uWSGI and nginx configuration files should work fine in
most cases.

.. code-block:: shell

    ln -s /etc/uwsgi/apps-available/indico.ini /etc/uwsgi/apps-enabled/indico.ini
    cat > /etc/uwsgi/apps-available/indico.ini <<'EOF'
    [uwsgi]
    uid = indico
    gid = nginx

    processes = 4
    enable-threads = false
    chmod-socket = 770
    socket = /opt/indico/web/uwsgi.sock
    stats = /opt/indico/web/uwsgi-stats.sock
    protocol = uwsgi

    master = true
    auto-procname = true
    procname-prefix-spaced = indico
    disable-logging = true

    plugin = python
    single-interpreter = true

    touch-reload = /opt/indico/web/indico.wsgi
    wsgi-file = /opt/indico/web/indico.wsgi
    virtualenv = /opt/indico/.venv

    vacuum = true
    buffer-size = 20480
    memory-report = true
    max-requests = 2500
    harakiri = 900
    harakiri-verbose = true
    reload-on-rss = 2048
    evil-reload-on-rss = 8192
    EOF


.. note::

    Replace ``YOURHOSTNAME`` in the next file with the hostname on which
    your Indico instance should be available, e.g. ``indico.yourdomain.com``


.. code-block:: shell

    cat > /etc/nginx/conf.d/indico.conf <<'EOF'
    server {
      listen 80;
      listen [::]:80;
      server_name YOURHOSTNAME;
      return 301 https://$server_name$request_uri;
    }

    server {
      listen       *:443 ssl http2;
      listen       [::]:443 ssl http2 default ipv6only=on;
      server_name  YOURHOSTNAME;

      ssl on;

      ssl_certificate           /etc/ssl/nginx/indico.crt;
      ssl_certificate_key       /etc/ssl/nginx/indico.key;
      ssl_session_cache         shared:SSL:10m;
      ssl_session_timeout       5m;
      ssl_protocols             TLSv1 TLSv1.1 TLSv1.2;
      ssl_ciphers               ECDHE-ECDSA-CHACHA20-POLY1305:ECDHE-RSA-CHACHA20-POLY1305:ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384:DHE-RSA-AES128-GCM-SHA256:DHE-RSA-AES256-GCM-SHA384:ECDHE-ECDSA-AES128-SHA256:ECDHE-RSA-AES128-SHA256:ECDHE-ECDSA-AES128-SHA:ECDHE-RSA-AES256-SHA384:ECDHE-RSA-AES128-SHA:ECDHE-ECDSA-AES256-SHA384:ECDHE-ECDSA-AES256-SHA:ECDHE-RSA-AES256-SHA:DHE-RSA-AES128-SHA256:DHE-RSA-AES128-SHA:DHE-RSA-AES256-SHA256:DHE-RSA-AES256-SHA:ECDHE-ECDSA-DES-CBC3-SHA:ECDHE-RSA-DES-CBC3-SHA:EDH-RSA-DES-CBC3-SHA:AES128-GCM-SHA256:AES256-GCM-SHA384:AES128-SHA256:AES256-SHA256:AES128-SHA:AES256-SHA:DES-CBC3-SHA:!DSS;
      ssl_prefer_server_ciphers on;

      access_log            /opt/indico/log/nginx/access.log combined;
      error_log             /opt/indico/log/nginx/error.log;

      location /.xsf/indico/ {
        internal;
        alias /opt/indico/;
      }

      location ~ ^/static/assets/(core|(?:plugin|theme)-[^/]+)/(.*)$ {
        alias /opt/indico/assets/$1/$2;
        access_log off;
      }

      location ~ ^/(ihelp|css|images|js|static(?!/plugins|/assets|/themes|/custom))(/.*)$ {
        alias /opt/indico/web/htdocs/$1$2;
        access_log off;
      }

      location /robots.txt {
        alias /opt/indico/web/htdocs/robots.txt;
        access_log off;
      }

      location / {
        root  /var/empty/nginx;
        include /etc/nginx/uwsgi_params;
        uwsgi_pass unix:/opt/indico/web/uwsgi.sock;
        uwsgi_param UWSGI_SCHEME $scheme;
        uwsgi_read_timeout 15m;
        uwsgi_buffers 32 32k;
        uwsgi_busy_buffers_size 128k;
        uwsgi_hide_header X-Sendfile;
        client_max_body_size 1G;
      }
    }
    EOF


.. _deb-ssl:

4. Create an SSL Certificate
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

First, create the folders for the certificate/key and set restrictive
permissions on them:

.. code-block:: shell

    mkdir /etc/ssl/nginx
    chown root:root /etc/ssl/nginx/
    chmod 700 /etc/ssl/nginx

If you are just trying out Indico you can simply use a self-signed
certificate (your browser will show a warning which you will have
to confirm when accessing your Indico instance for the first time).


.. note::

    Do not forget to replace ``YOURHOSTNAME`` with the same value
    you used above

.. code-block:: shell

    openssl req -x509 -nodes -newkey rsa:4096 -subj /CN=YOURHOSTNAME -keyout /etc/ssl/nginx/indico.key -out /etc/ssl/nginx/indico.crt


While a self-signed certificate works for testing, it is not suitable
for a production system.  You can either buy a certificate from any
commercial certification authority or get a free one from
`Let's Encrypt`_. Once you have a proper key/certificate, save them
as ``/etc/ssl/nginx/indico.key`` and ``/etc/ssl/nginx/indico.crt``.


.. _deb-install:

5. Install Indico
^^^^^^^^^^^^^^^^^

Celery runs as a background daemon. Add a systemd unit file for it:

.. code-block:: shell

    cat > /etc/systemd/system/indico-celery.service <<'EOF'
    [Unit]
    Description=Indico Celery
    After=network.target

    [Service]
    ExecStart=/opt/indico/.venv/bin/indico celery worker -B
    Restart=always
    SyslogIdentifier=indico-celery
    User=indico
    Group=nginx
    Type=simple

    [Install]
    WantedBy=multi-user.target
    EOF
    systemctl daemon-reload


Now create a user that will be used to run Indico and switch to it:

.. code-block:: shell

    useradd -rm -g nginx -d /opt/indico -s /bin/bash indico
    su - indico


You are now ready to install Indico:

.. code-block:: shell

    virtualenv ~/.venv
    source ~/.venv/bin/activate
    pip install -U pip setuptools
    pip install indico

.. note::

    If you use a custom-built indico wheel, use ``pip install /path/to/indico-*.whl``
    instead of ``pip install indico``


.. _deb-config:

6. Configure Indico
^^^^^^^^^^^^^^^^^^^

Once Indico is installed, you can run the configuration wizard.  You can
keep the defaults for most options, but make sure to use ``https://YOURHOSTNAME``
when prompted for the Indico URL. Also specify valid email addresses when asked
and enter a valid SMTP server Indico can use to send emails.  When asked for the
default timezone make sure this is the main time zone used in your Indico instance.

.. code-block:: shell

    indico setup wizard


Now finish setting up the directory structure and permissions:

.. code-block:: shell

    mkdir ~/log/nginx
    chmod go-rwx ~/* ~/.*
    chmod 710 ~/ ~/archive ~/assets ~/cache ~/log ~/tmp
    chmod 750 ~/web ~/.venv
    chmod g+w ~/log/nginx
    echo -e "\nStaticFileMethod = ('xaccelredirect', {'/opt/indico': '/.xsf/indico'})" >> ~/etc/indico.conf


7. Create database schema
^^^^^^^^^^^^^^^^^^^^^^^^^

Finally, you can create the database schema and switch back to *root*:

.. code-block:: shell

    indico db prepare
    exit


.. _deb-launch:

8. Launch Indico
^^^^^^^^^^^^^^^^

You can now start Indico and set it up to start automatically when the
server is rebooted:

.. code-block:: shell

    systemctl restart uwsgi.service nginx.service indico-celery.service
    systemctl enable uwsgi.service nginx.service postgresql.service redis-server.service indico-celery.service


.. _deb-user:

9. Create an Indico user
^^^^^^^^^^^^^^^^^^^^^^^^

Access ``https://YOURHOSTNAME`` in your browser and follow the steps
displayed there to create your initial user.


.. _PostgreSQL wiki: https://wiki.postgresql.org/wiki/YUM_Installation#Configure_your_YUM_repository
.. _Let's Encrypt: https://letsencrypt.org/
