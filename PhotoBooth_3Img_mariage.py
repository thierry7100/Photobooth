#!/usr/bin/python3

from __future__ import print_function
import httplib2
import os, sys
import subprocess

from picamera import PiCamera
from time import *
from gpiozero import Button, LED, PWMLED
from PIL import Image

from apiclient import discovery
from oauth2client import client
from oauth2client import tools
from oauth2client.file import Storage
from apiclient.http import MediaFileUpload
from apiclient.discovery import build
from threading import Thread
import pygame
from pygame.locals import *
import random
import configparser

# If modifying these scopes, delete your previously saved credentials
# at ~/.credentials/drive_photobooth.json
SCOPES = 'https://www.googleapis.com/auth/drive.file'

APPLICATION_NAME = 'PhotoMariage'

#   Broches utilisées au niveau GPiO
#   Bouton pour lancer le cycle photo 
buttonPhoto = Button(17)
ledPhoto = PWMLED(18)       #   et la led incorporée au bouton
#   Bouton pour garder les photos prises
buttonKeep = Button(22)
#   Bouton pour jeter les photos prises
buttonThrow = Button(27)
#   Led utilisée pour indiquer qu'un transfert vers Google Drive est en cours
ledDrive = LED(12)

#   Variables globales
camera = PiCamera()
ButtonThrowIsPressed = 0
ButtonKeepIsPressed = 0

#   Les divers fichiers utilisés pour les effets sonores
SoundFiles = ['on fait cheese Cath.wav', 'ouistiti Isa.wav', 'et on sourit Cath.wav', 'cheese Isa.wav', 'Cheese Isa Cath.wav', 'Ouistiti Isa Cath.wav', 'Allez souriez Isa.wav']
NbSoundFiles = 7        #   Nombre de fichiers présents
random.seed()           #   Initialise le générateur aléatoire

#   Taille de l'écran
#   Utilise un écran 800x480 bon marché
Screen_Size_X   = 800
Screen_Size_Y = 480

#   Taille utilisée pour le Preview de la camera
#   Doit être au format 4/3 pour respecter les dimensions
#   Utilise la zone maximale de l'écran en respectant le format
Screen_Size_Preview_X  = 640
Screen_Size_Preview_Y  = 480

#   Nombre de transferts en cours vers Google Drive
NbUpload = 0

#   Résolution caméra Raspberry. 
#   Utilise la demi résolution, les images sont de qualité suffisante, et beaucoup moins lourd en charge CPU
Camera_X_Resolution = 1640
Camera_Y_Resolution = 1232

#   Les photos sont regroupées par 4 pour impression.
#   Positionne les 4 images dans l'image finale de manière centrée
#   L'impression utilise du papier 10x15, crée une image avec le même rapport (1.5)

QuadPhoto_Size_Y = 2730
QuadPhoto_Size_X = 4096

#Première image en haut à gauche
QuadPhoto_Img0_X  = 240
QuadPhoto_Img0_Y  = 104

#Seconde image en haut à droite
QuadPhoto_Img1_X  = 2210
QuadPhoto_Img1_Y  = QuadPhoto_Img0_Y                                           #   Centre l'image dans le quart en haut à droite

QuadPhoto_Img2_X = QuadPhoto_Img0_X
QuadPhoto_Img2_Y = 1466


camera.resolution = (Camera_X_Resolution, Camera_Y_Resolution)  #Travaille a demi resolution, suffisant pour l'application choisie et le regroupement des photos en 10x15

camera.annotate_text_size = 160
camera.hflip = False # horizontal flip to see as in a mirror
# this is not Needed, just add display_rotate=2 or lcd_rotate=2 in /boot/config.txt
camera.vflip = False # vertical flip if screen is upside down

config_file = '/home/pi/photobooth/photoBooth.cfg'
config = configparser.ConfigParser()
config.read(config_file)

#These fields are read from config file
PrinterName = config['Printer']['PrinterName']
NbPrintCopy = int(config['Printer']['NbCopies'])
ImageFond = config['Picture4']['PictureName']
ClientSecretFile = config['Upload']['SecretFile']
CredentialFileName=config['Upload']['CredentialFile']
WorkingDir = config['Directories']['WorkingDir']
PhotoDir = config['Directories']['PhotoDir']
UploadGoogleDrive = int(config['Upload']['GoogleDrive'])


def get_credentials():
    """Gets valid user credentials from storage.

    If nothing has been stored, or if the stored credentials are invalid,
    the OAuth2 flow is completed to obtain the new credentials.

    Returns:
        Credentials, the obtained credential.
    """
    #print("Looking for credentials")
    home_dir = os.path.expanduser('~')
    credential_dir = os.path.join(home_dir, '.credentials')
    if not os.path.exists(credential_dir):
        os.makedirs(credential_dir)
    credential_path = os.path.join(credential_dir, CredentialFileName)
    print ("get_credentials path :", credential_path)
    store = Storage(credential_path)
    #print("get_credentials #1")
    credentials = store.get()
    #print("get_credentials #2")
    if not credentials or credentials.invalid:
        print("get_credentials : no credentials yet...")
        flow = client.flow_from_clientsecrets(ClientSecretFile, SCOPES)
        flow.user_agent = APPLICATION_NAME
        credentials = tools.run_flow(flow, store)
        print('Storing credentials to ' + credential_path)
    #else:
    #   print("get_credentials OK")
    return credentials

def uploadToDrive (fname):
    """   Envoie un fichier vers Google Drive
    
    Ne retourne rien
    """
    if UploadGoogleDrive == 0:
        return
    credentials = get_credentials()
    http = credentials.authorize(httplib2.Http())
    service = discovery.build('drive', 'v3', http=http)

    folder_id = None;
    results = service.files().list(pageSize=10,fields="nextPageToken, files(id, name)").execute()
    items = results.get('files', [])
    if not items:
        print('No files found.')
    else:
        print('Files:')
        for item in items:
            #print('{0} ({1})'.format(item['name'], item['id']))
            if item['name'] == "PhotoMariage":
                folder_id = item['id']
    if not folder_id:
        # create dir
        file_metadata = {
            'name': 'PhotoMariage',
            'mimeType': 'application/vnd.google-apps.folder'
        }
        file = service.files().create(body=file_metadata, fields='id').execute()
        print ('Created Folder ID: %s' % file.get('id'))
        folder_id = file.get('id')
    # upload file
    file_metadata = {'name': os.path.basename(fname), 'parents': [folder_id] }
    print("begin uploading ", fname)
    media = MediaFileUpload(fname, mimetype='image/jpeg', resumable=True)
    #print("end Upload") 
    file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
    print ("Created File : %s (%s)" % (file.get('name'), file.get('id')))

def getImgScreenResolution (fname):
    """ Charge une image dans un buffer compatible avec la caméra Raspberry pour surimpression
        Le buffer fait Screen_Size_X x Screen_Size_Y, identique à la taille de l'écran
        L'image source doit être en mode RGBA (PNG par exemple) avec une taille égale à celle de l'écran
        Colle l'image initiale en haut à gauche de la zone
        
        Retourne l'image crée
    """
    # Charge l'image qui est de la taille écran
    img = Image.open(fname)
    print("Image : ", fname, " Size ", img.size[0], "x", img.size[1])
    if img.size[0] % 32 != 0 or img.size[1] % 16 != 0:
        # Create an image padded to the required size with mode 'RGBA'
        pad = Image.new('RGBA', (Screen_Size_X, Screen_Size_Y)) # Paste the original image into the padded one, set at raspberry camera resolution and rounded for 32 bits(x) and 16 bit (y)
        pad.paste(img, (0, 0))
        print("PAD : ", fname, " Size ", pad.size[0], "x", pad.size[1])
        return pad
    else:
        return img

def getImgResizeScreenResolution (fname):
    """ Charge une image dans un buffer compatible avec la caméra Raspberry pour surimpression
        Le buffer fait Screen_Size_X x Screen_Size_Y, identique à la taille de l'écran
        Si 'image n'est pas 
        Colle l'image initiale en haut à gauche de la zone
        
        Retourne l'image crée
    """
    img = Image.open(fname)
    print("Original Image : ", fname, " Size ", img.size[0], "x", img.size[1])
    img = img.resize((Screen_Size_X, Screen_Size_Y))
    print("Image After Resizing: ", fname, " Size ", img.size[0], "x", img.size[1])
    # Create an image padded to the required size with mode 'RGBA', always create this image as source image may not be RGBA
    pad = Image.new('RGBA', (Screen_Size_X, Screen_Size_Y)) # Paste the original image into the padded one, set at raspberry camera resolution and rounded for 32 bits(x) and 16 bit (y)
    pad.paste(img, (0, 0))
    print("PAD : ", fname, " Size ", pad.size[0], "x", pad.size[1])
    return pad

def PressThrowButton():
    """ Fonction appelée quand le bouton "Jeter" est pressé
        Se contente de positionner la variable globale correspondante
        
        Ne retourne rien
    """
    global ButtonThrowIsPressed
    #print ("Bouton Rouge\n")
    ButtonThrowIsPressed = 1

def PressKeepButton():
    """ Fonction appelée quand le bouton "garder" est pressé
        Se contente de positionner la variable globale correspondante
        
        Ne retourne rien
    """
    global ButtonKeepIsPressed
    #print ("Bouton blanc\n")
    ButtonKeepIsPressed = 1

    
    
class thUpload(Thread):
    """ Classe utilisée pour envoyer les fichiers créés vers Google Drive
        Utilise des threads pour faire plusieurs envois en parallèle
    """
    def __init__(self, fname):
        Thread.__init__(self)
        self.fname = fname          #   Nom du fichier à envoyer
    def run (self):
        global NbUpload             #   Utilise une variable globale pour compter le nombre de transferts en cours.
        try:
            NbUpload += 1
            ledDrive.on()           #   Allume la LED, au moins un tarnsfert en cours
            uploadToDrive ( self.fname )
            NbUpload -= 1
            if NbUpload <= 0:
                NbUpload = 0        #   Empeche de devenir négatif (erreur) !
                print("Fin transfert vers Google drive")
                ledDrive.off()      #   Eteint la Led Drive
        except:
            print ("cannot upload picture %s to drive. (%s)" % (self.fname, sys.exc_info()[0]) , file=sys.stderr)
            NbUpload -= 1
            if NbUpload <= 0:
                NbUpload = 0        #   Empeche de devenir négatif (erreur) !
                ledDrive.off()      #   Eteint la Led Drive


# First use working directory
os.chdir(WorkingDir) 
#   Charge les images qui vont être utilisées en overlay
#   La taille des imlages est celle de l'écran
ImageAccueil = getImgScreenResolution ("Accueil.png")
FondEcran = getImgScreenResolution ("Fond.png")
SecondePhoto = getImgScreenResolution("SecondePhoto.png");
DernierePhoto = getImgScreenResolution("DernierePhoto.png");
apresPhoto = getImgScreenResolution ("ApresPhoto2.png")
waits = []
for i in range(3):
    waits.append(getImgScreenResolution ("%d.png" % (i+1)))

#   Initialise l'image composite
#   Crée une image de la taille finale et colle la 4ème (fixe) en bas à droite
print("Taille image Quatre = (", QuadPhoto_Size_X, ",", QuadPhoto_Size_Y, ")")
print("Position images, 0=(", QuadPhoto_Img0_X, ",", QuadPhoto_Img0_Y, ")  1=(",  QuadPhoto_Img1_X, ",", QuadPhoto_Img1_Y, ")  2=(",  QuadPhoto_Img2_X, ",", QuadPhoto_Img2_Y, ")") 
QuadImage = Image.new("RGB",(QuadPhoto_Size_X, QuadPhoto_Size_Y), (255, 255, 255) )        #Crée l'image composite (init en blanc)
ImageQuatre = Image.open(ImageFond)
QuadImage.paste(ImageQuatre, ( 0, 0) )                # Copie l'image
#   Initialise la partie son, basée sur pygames
pygame.mixer.init()
pygame.mixer.music.set_volume(1.0)

# add an overlay which cut the picture at the right size (camera format is 4/3)
o1 = camera.add_overlay(FondEcran.tobytes(), size=(Screen_Size_X,Screen_Size_Y), format='rgba', layer=1, vflip=camera.vflip, hflip=camera.vflip)
camera_preview = camera.start_preview(resolution=(Screen_Size_Preview_X, Screen_Size_Preview_Y))    #start preview with format 4/3
camera_preview.fullscreen = True
while True:
    try:
        buttonKeep.when_pressed = None
        buttonThrow.when_pressed = None

        # Affiche les instructions (appyer sur gros bouton vert) au dessus de l'image de la camera
        # Reduit l'image de la camera au dimensions de l'affichage et non à sa résolution réelle.
        # Utilise un overlay 32 bits (RGBA) pour profiter du paramètre transparence des fichiers PNG
        # Cela économise beaucoup de calculs sur le raspberry
        # Les paramètres de Flip (H et V) sont positionnés ici. PAr défaut HFlip = True et VFlip = False
        # Le niveau d'overlay doit être plus grand que 2 qui est le niveau par défaut de la caméra en mode preview
        o3 = camera.add_overlay(ImageAccueil.tobytes(), size=(Screen_Size_X,Screen_Size_Y), format='rgba', layer=3, vflip=camera.vflip, hflip=camera.vflip)

        # Fait clignoter le bouton vert pour inciter à appuyer dessus
        ledPhoto.pulse(2,2)
        buttonPhoto.wait_for_press()
        # Si le code ici est atteint, le bouton a été pressé.
        # Passe en phase prise de photo
        # Clignotement différent bouton
        ledPhoto.pulse (fade_in_time=0.125, fade_out_time=0.125, n=16, background=True)
        # Enlève l'image overlay donnat les instructions
        camera.remove_overlay(o3)
        
        # Première photo
        # Charge le son qui va être joué
        indexSound = random.randrange(7)
        pygame.mixer.music.load(SoundFiles[indexSound])
        # Affiche 3 .. 2 .. 1 avant de prendre la photo en Overlay au dessus de l'image
        for i in range(2, -1, -1):
            o3 = camera.add_overlay(waits[i].tobytes(),  size=(Screen_Size_X,Screen_Size_Y), format='rgba', layer=3, vflip=camera.vflip, hflip=camera.vflip)
            if i == 0:
                # Au dernier pas, joue le son qui dure environ 1s, cohérent avec l'attente
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() == True:
                    continue
            else:
                #sinon attent 1s avant de changer d'image
                sleep(1)
            camera.remove_overlay(o3)
        # capture still image from camera
        outfile1 = PhotoDir + '/MP-1-%s.jpg' % ( strftime("%Y%m%d-%H%M%S", localtime() ) )
        camera.capture( outfile1 )

        # Seconde photo

        o3 = camera.add_overlay(SecondePhoto.tobytes(),  size=(Screen_Size_X,Screen_Size_Y), format='rgba', layer=3, vflip=camera.vflip, hflip=camera.vflip)
        #Ajoute l'image 1 capturée, fait cela maintenant avec le texte affiché
        Image1 = Image.open(outfile1)
        QuadImage.paste(Image1, (QuadPhoto_Img0_X, QuadPhoto_Img0_Y))
        # upload pictures to google drive if enabled
        if UploadGoogleDrive > 0:
            th = thUpload (outfile1)
            th.start()
        del Image1
        sleep(1)        #Attente le temps de lire le texte...
        camera.remove_overlay(o3)
        # Charge le son qui va être joué
        indexSound = random.randrange(7)
        pygame.mixer.music.load(SoundFiles[indexSound])
        # Affiche 2 .. 1 avant de prendre la photo en Overlay au dessus de l'image
        for i in range(1, -1, -1):
            o3 = camera.add_overlay(waits[i].tobytes(),  size=(Screen_Size_X,Screen_Size_Y), format='rgba', layer=3, vflip=camera.vflip, hflip=camera.vflip)
            if i == 0:
                # Au dernier pas, joue le son qui dure environ 1s, cohérent avec l'attente
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() == True:
                    continue
            else:
                #sinon attent 1s avant de changer d'image
                sleep(1)
            camera.remove_overlay(o3)
        # capture still image from camera
        outfile2 = PhotoDir + '/MP-2-%s.jpg' % ( strftime("%Y%m%d-%H%M%S", localtime() ) )
        camera.capture( outfile2 )

        # Troisième et dernière photo

        o3 = camera.add_overlay(DernierePhoto.tobytes(),  size=(Screen_Size_X,Screen_Size_Y), format='rgba', layer=3, vflip=camera.vflip, hflip=camera.vflip)
        #Ajoute l'image 3 capturée, fait cela maintenant avec le texte affiché
        Image2 = Image.open(outfile2)
        QuadImage.paste(Image2, (QuadPhoto_Img1_X, QuadPhoto_Img1_Y))
        # upload pictures to google drive
        if UploadGoogleDrive > 0:
            th = thUpload (outfile2)
            th.start()
        del Image2
        sleep(1)
        camera.remove_overlay(o3)
        # Charge le son qui va être joué
        indexSound = random.randrange(7)
        pygame.mixer.music.load(SoundFiles[indexSound])
        # Affiche 2 .. 1 avant de prendre la photo en Overlay au dessus de l'image
        for i in range(1, -1, -1):
            o3 = camera.add_overlay(waits[i].tobytes(),  size=(Screen_Size_X,Screen_Size_Y), format='rgba', layer=3, vflip=camera.vflip, hflip=camera.vflip)
            if i == 0:
                # Au dernier pas, joue le son qui dure environ 1s, cohérent avec l'attente
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy() == True:
                    continue
            else:
                #sinon attent 1s avant de changer d'image
                sleep(1)
            camera.remove_overlay(o3)
        # capture still image from camera
        outfile3 = PhotoDir+'/MP-3-%s.jpg' % ( strftime("%Y%m%d-%H%M%S", localtime() ) )
        camera.capture( outfile3 )

         #Ajoute l'image 3 capturée
        Image3 = Image.open(outfile3)
        QuadImage.paste(Image3, (QuadPhoto_Img2_X, QuadPhoto_Img2_Y))
        # upload pictures to google drive
        if UploadGoogleDrive > 0:
            th = thUpload (outfile3)
            th.start()
        del Image3

        outfile4 =  PhotoDir + '/MP-4-%s.jpg' % ( strftime("%Y%m%d-%H%M%S", localtime() ) )
        QuadImage.save(outfile4, 'jpeg', quality=85)

        #  Phase suivante : on garde ou on jette ?
        ledPhoto.value = 0
        KeepPicture = 1		#Par defaut on garde
        buttonKeep.when_pressed = PressKeepButton
        buttonThrow.when_pressed = PressThrowButton
        ButtonThrowIsPressed = 0
        ButtonKeepIsPressed = 0

        #Affiche l'image composite
        outover = getImgResizeScreenResolution(outfile4)
        o3 = camera.add_overlay(outover.tobytes(), size=(Screen_Size_X,Screen_Size_Y), format='rgba', layer=3)
        #explain that picture will be displayed and user can choose to keep or throw
        o4 = camera.add_overlay(apresPhoto.tobytes(),  size=(Screen_Size_X,Screen_Size_Y), format='rgba', layer=4, vflip=camera.vflip, hflip=camera.vflip)
        # wait for 10s for user pressing either Keep or Throw.
        # if timeout, the picture will be kept.
        StartTimeAfter = time()
        print("attente choix utilisateur time =", StartTimeAfter)
        while time() - StartTimeAfter < 10:
            if ButtonThrowIsPressed > 0:
                StartTimeAfter -= 10
                KeepPicture = 0
                print("on jette")
            if ButtonKeepIsPressed > 0:
                StartTimeAfter -= 10
                print("on garde")
        print("Choix utilisateur : ", KeepPicture, " at", time())
        buttonKeep.when_pressed = None
        buttonThrow.when_pressed = None
        if KeepPicture > 0:
            # upload pictures to google drive
            if UploadGoogleDrive > 0:
                th = thUpload (outfile4)
                th.start()
            #   Et on imprime...
            if NbPrintCopy > 0:
                print("Impression ", outfile4)
                #Commande a executer lp -d EPSON_XP_860_WIFI -n 2 -o landscape -o fit-to-page FileName
                subprocess.Popen(['/usr/bin/lp', '-d', PrinterName, '-n', str(NbPrintCopy), '-o', 'landscape', '-o', 'fit-to-page', outfile4])
        else:
            os.remove(outfile4)
            print("Remove file")
        camera.remove_overlay(o4)
        camera.remove_overlay(o3)
        camera.annotate_text = ''
    except KeyboardInterrupt:
        camera.remove_overlay(o1)
        camera.stop_preview()
        camera.close()
        break

camera.stop_preview()
camrera.close()

