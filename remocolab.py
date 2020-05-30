import apt, apt.debfile
import pathlib, stat, shutil, urllib.request, subprocess, getpass, time, tempfile
import secrets, json, re
import IPython.utils.io

def _installPkg(cache, name):
  pkg = cache[name]
  if pkg.is_installed:
    print(f"{name} zaten yüklenmiş")
  else:
    print(f"Yükleniyor {name}")
    pkg.mark_install()

def _installPkgs(cache, *args):
  for i in args:
    _installPkg(cache, i)

def _download(url, path):
  try:
    with urllib.request.urlopen(url) as response:
      with open(path, 'wb') as outfile:
        shutil.copyfileobj(response, outfile)
  except:
    print("İndirme başarısız oldu ", url)
    raise

def _get_gpu_name():
  r = subprocess.run(["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"], stdout = subprocess.PIPE, universal_newlines = True)
  if r.returncode != 0:
    return None
  return r.stdout.strip()

def _check_gpu_available():
  gpu_name = _get_gpu_name()
  if gpu_name == None:
    print("Bu makine GPU ile çalışmıyor.GPU için Runtime / Change Runtime kısmından GPU seçiniz")
  elif gpu_name == "Tesla K80":
    print("Uyarı! Bu makineye atanmış olan GPU Tesla K80.")
    print("Makineyi resetleyerek daha güçlü bir GPU almayı deneyebilirsiniz.")
  else:
    return True

  return IPython.utils.io.ask_yes_no("Devam etmek istiyor musunuz? [y/n]")

def _setupSSHDImpl(ngrok_token, ngrok_region):
  #apt-get update
  #apt-get upgrade
  cache = apt.Cache()
  cache.update()
  cache.open(None)
  cache.upgrade()
  cache.commit()

  subprocess.run(["unminimize"], input = "y\n", check = True, universal_newlines = True)
  
  subprocess.run(["add-apt-repository", "ppa:stebbins/handbrake-git-snapshots"])
  subprocess.run(["apt-get", "update"])
  subprocess.run(["wget", "-q", "-O", "-", "https://mkvtoolnix.download/gpg-pub-moritzbunkus.txt", "|", "sudo", "apt-key", "add", "-"]
  subprocess.run(["sudo", "apt-key", "add", "-"])
  with open("/etc/apt/sources.list.d/mkvtoolnix.download.list", "a") as f:
    f.write("\n\ndeb https://mkvtoolnix.download/ubuntu/ bionic main\ndeb-src https://mkvtoolnix.download/ubuntu/ bionic main\n")
    
  subprocess.run(["apt-get", "update"])
  subprocess.run(["apt", "install", "mkvtoolnix", "mkvtoolnix-gui"])
 
  subprocess.run(["apt-get", "update"])
  subprocess.run(["wget", "-q", "-O", "-", "https://mkvtoolnix.download/gpg-pub-moritzbunkus.txt", "|", "sudo", "apt-key", "add", "-"]
  with open("/etc/apt/sources.list.d/mkvtoolnix.download.list", "a") as f:
    f.write("\n\ndeb https://mkvtoolnix.download/ubuntu/ bionic main\ndeb-src https://mkvtoolnix.download/ubuntu/ bionic main\n")
    
  subprocess.run(["apt-get", "update"])
  
  _installPkg(cache, "openssh-server")
  cache.commit()
  
  _installPkg(cache, "mediainfo-gui")
  cache.commit()
  
  
  #Reset host keys
  for i in pathlib.Path("/etc/ssh").glob("ssh_host_*_key"):
    i.unlink()
  subprocess.run(
                  ["ssh-keygen", "-A"],
                  check = True)

  #Prevent ssh session disconnection.
  with open("/etc/ssh/sshd_config", "a") as f:
    f.write("\n\nClientAliveInterval 120\n")

  msg = ""
  msg += "Sunucunun ECDSA anahtar parmakizi:\n"
  ret = subprocess.run(
                ["ssh-keygen", "-lvf", "/etc/ssh/ssh_host_ecdsa_key.pub"],
                stdout = subprocess.PIPE,
                check = True,
                universal_newlines = True)
  msg += ret.stdout + "\n"

  _download("https://bin.equinox.io/c/4VmDzA7iaHb/ngrok-stable-linux-amd64.zip", "ngrok.zip")
  shutil.unpack_archive("ngrok.zip")
  pathlib.Path("ngrok").chmod(stat.S_IXUSR)

  root_password = secrets.token_urlsafe()
  user_password = secrets.token_urlsafe()
  user_name = "bitturk"
  msg += "✂️"*24 + "\n"
  msg += f"root şifresi: {root_password}\n"
  msg += f"{user_name} şifresi: {user_password}\n"
  msg += "✂️"*24 + "\n"
  subprocess.run(["useradd", "-s", "/bin/bash", "-m", user_name])
  subprocess.run(["adduser", user_name, "sudo"], check = True)
  subprocess.run(["chpasswd"], input = f"root:{root_password}", universal_newlines = True)
  subprocess.run(["chpasswd"], input = f"{user_name}:{user_password}", universal_newlines = True)
  subprocess.run(["service", "ssh", "restart"])

  if not pathlib.Path('/root/.ngrok2/ngrok.yml').exists():
    subprocess.run(["./ngrok", "authtoken", ngrok_token])

  ngrok_proc = subprocess.Popen(["./ngrok", "tcp", "-region", ngrok_region, "22"])
  time.sleep(2)
  if ngrok_proc.poll() != None:
    raise RuntimeError("Failed to run ngrok. Return code:" + str(ngrok_proc.returncode) + "\nSee runtime log for more info.")

  with urllib.request.urlopen("http://localhost:4040/api/tunnels") as response:
    url = json.load(response)['tunnels'][0]['public_url']
    m = re.match("tcp://(.+):(\d+)", url)

  hostname = m.group(1)
  port = m.group(2)

  ssh_common_options =  "-o UserKnownHostsFile=/dev/null -o VisualHostKey=yes"
  msg += "---\n"
  msg += "Sadece SSH server olarak bağlanmak için gerekli komut :\n"
  msg += "✂️"*24 + "\n"
  msg += f"ssh {ssh_common_options} -p {port} {user_name}@{hostname}\n"
  msg += "✂️"*24 + "\n"
  msg += "---\n"
  msg += "VNC ile bağlanmak için gerekli olan komut:\n"
  msg += "✂️"*24 + "\n"
  msg += f"ssh {ssh_common_options} -L 5901:localhost:5901 -p {port} {user_name}@{hostname}\n"
  msg += "✂️"*24 + "\n"
  return msg

def _setupSSHDMain(ngrok_region, check_gpu_available):
  if check_gpu_available and not _check_gpu_available():
    return (False, "")

  print("---")
  print("https://dashboard.ngrok.com/auth adresindeki Your Authtoken kısmındaki kodu buraya yapıştırın.")
  print("(Kodu yapıştırdıktan sonra ENTER tuşuna basın. Not : ngrok üyeliği gerekmektedir)")
  #Set your ngrok Authtoken.
  ngrok_token = getpass.getpass()

  if not ngrok_region:
    print("SSH Tunnelling için bölge seçin:")
    print("us - Amerika (Ohio)")
    print("eu - Avrupa (Frankfurt)")
    print("ap - Asya/Pasifik (Singapore)")
    print("au - Avustralya (Sydney)")
    print("sa - Güney Amerika (Sao Paulo)")
    print("jp - Japonya (Tokyo)")
    print("in - Hindistan (Mumbai)")
    ngrok_region = region = input()

  return (True, _setupSSHDImpl(ngrok_token, ngrok_region))

def setupSSHD(ngrok_region = None, check_gpu_available = False):
  s, msg = _setupSSHDMain(ngrok_region, check_gpu_available)
  print(msg)

def _setup_nvidia_gl():
  # Install TESLA DRIVER FOR LINUX X64.
  # Kernel module in this driver is already loaded and cannot be neither removed nor updated.
  # (nvidia, nvidia_uvm, nvidia_drm. See dmesg)
  # Version number of nvidia driver for Xorg must match version number of these kernel module.
  # But existing nvidia driver for Xorg might not match.
  # So overwrite them with the nvidia driver that is same version to loaded kernel module.
  ret = subprocess.run(
                  ["nvidia-smi", "--query-gpu=driver_version", "--format=csv,noheader"],
                  stdout = subprocess.PIPE,
                  check = True,
                  universal_newlines = True)
  nvidia_version = ret.stdout.strip()
  nvidia_url = "https://us.download.nvidia.com/tesla/{0}/NVIDIA-Linux-x86_64-{0}.run".format(nvidia_version)
  _download(nvidia_url, "nvidia.run")
  pathlib.Path("nvidia.run").chmod(stat.S_IXUSR)
  subprocess.run(["./nvidia.run", "--no-kernel-module", "--ui=none"], input = "1\n", check = True, universal_newlines = True)

  #https://virtualgl.org/Documentation/HeadlessNV
  subprocess.run(["nvidia-xconfig",
                  "-a",
                  "--allow-empty-initial-configuration",
                  "--virtual=1920x1080",
                  "--busid", "PCI:0:4:0"],
                 check = True
                )

  with open("/etc/X11/xorg.conf", "r") as f:
    conf = f.read()
    conf = re.sub('(Section "Device".*?)(EndSection)',
                  '\\1    MatchSeat      "seat-1"\n\\2',
                  conf,
                  1,
                  re.DOTALL)
  #  conf = conf + """
  #Section "Files"
  #    ModulePath "/usr/lib/xorg/modules"
  #    ModulePath "/usr/lib/x86_64-linux-gnu/nvidia-418/xorg/"
  #EndSection
  #"""

  with open("/etc/X11/xorg.conf", "w") as f:
    f.write(conf)

  #!service lightdm stop
  subprocess.run(["/opt/VirtualGL/bin/vglserver_config", "-config", "+s", "+f"], check = True)
  #user_name = "colab"
  #!usermod -a -G vglusers $user_name
  #!service lightdm start

  # Run Xorg server
  # VirtualGL and OpenGL application require Xorg running with nvidia driver to get Hardware 3D Acceleration.
  #
  # Without "-seat seat-1" option, Xorg try to open /dev/tty0 but it doesn't exists.
  # You can create /dev/tty0 with "mknod /dev/tty0 c 4 0" but you will get permision denied error.
  subprocess.Popen(["Xorg", "-seat", "seat-1", "-allowMouseOpenFail", "-novtswitch", "-nolisten", "tcp"])

def _setupVNC():
  libjpeg_ver = "2.0.3"
  virtualGL_ver = "2.6.3"
  turboVNC_ver = "2.2.5"

  libjpeg_url = "https://cfhcable.dl.sourceforge.net/project/libjpeg-turbo/{0}/libjpeg-turbo-official_{0}_amd64.deb".format(libjpeg_ver)
  virtualGL_url = "https://cfhcable.dl.sourceforge.net/project/virtualgl/{0}/virtualgl_{0}_amd64.deb".format(virtualGL_ver)
  turboVNC_url = "https://cfhcable.dl.sourceforge.net/project/turbovnc/{0}/turbovnc_{0}_amd64.deb".format(turboVNC_ver)

  _download(libjpeg_url, "libjpeg-turbo.deb")
  _download(virtualGL_url, "virtualgl.deb")
  _download(turboVNC_url, "turbovnc.deb")
  cache = apt.Cache()
  apt.debfile.DebPackage("libjpeg-turbo.deb", cache).install()
  apt.debfile.DebPackage("virtualgl.deb", cache).install()
  apt.debfile.DebPackage("turbovnc.deb", cache).install()

  _installPkgs(cache, "xfce4", "xfce4-terminal" , "xfce4-goodies", "firefox", "qbittorrent", "filezilla", "handbrake-gtk", "handbrake-cli" )
  cache.commit()
  
  vnc_sec_conf_p = pathlib.Path("/etc/turbovncserver-security.conf")
  vnc_sec_conf_p.write_text("""\
no-remote-connections
no-httpd
no-x11-tcp-connections
""")

  gpu_name = _get_gpu_name()
  if gpu_name != None:
    _setup_nvidia_gl()

  vncrun_py = tempfile.gettempdir() / pathlib.Path("vncrun.py")
  vncrun_py.write_text("""\
import subprocess, secrets, pathlib

vnc_passwd = secrets.token_urlsafe()[:8]
vnc_viewonly_passwd = secrets.token_urlsafe()[:8]
print("✂️"*24)
print("VNC yönetici şifresi: {}".format(vnc_passwd))
print("VNC sadece görüntüleme şifresi: {}".format(vnc_viewonly_passwd))
print("✂️"*24)
vncpasswd_input = "{0}\\n{1}".format(vnc_passwd, vnc_viewonly_passwd)
vnc_user_dir = pathlib.Path.home().joinpath(".vnc")
vnc_user_dir.mkdir(exist_ok=True)
vnc_user_passwd = vnc_user_dir.joinpath("passwd")
with vnc_user_passwd.open('wb') as f:
  subprocess.run(
    ["/opt/TurboVNC/bin/vncpasswd", "-f"],
    stdout=f,
    input=vncpasswd_input,
    universal_newlines=True)
vnc_user_passwd.chmod(0o600)
subprocess.run(
  ["/opt/TurboVNC/bin/vncserver"]
)

#Disable screensaver because no one would want it.
(pathlib.Path.home() / ".xscreensaver").write_text("mode: off\\n")
""")
  
  r = subprocess.run(
                    ["su", "-c", "python3 " + str(vncrun_py), "bitturk"],
                    check = True,
                    stdout = subprocess.PIPE,
                    universal_newlines = True)
  return r.stdout

def setupVNC(ngrok_region = None, check_gpu_available = True):
  stat, msg = _setupSSHDMain(ngrok_region, check_gpu_available)
  if stat:
    msg += _setupVNC()

  print(msg)
