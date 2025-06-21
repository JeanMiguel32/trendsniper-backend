from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
from dotenv import load_dotenv
import os
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from datetime import datetime, timedelta
import math
import yt_dlp
import tempfile
import uuid
import requests
import re
import yt_dlp
import tempfile
import uuid
from flask import send_file
import requests

# Chargement des variables d'environnement
load_dotenv()

app = Flask(__name__)
CORS(app)

# Configuration de l'API YouTube
YOUTUBE_API_KEY = os.getenv('YOUTUBE_API_KEY')
if not YOUTUBE_API_KEY:
    raise ValueError("❌ La clé API YouTube n'est pas configurée dans le fichier .env")

try:
    youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY, static_discovery=False)
    print("✅ Connexion à l'API YouTube réussie!")
except Exception as e:
    print(f"❌ Erreur lors de la connexion à l'API YouTube: {str(e)}")
    raise e

@app.route('/api/trends', methods=['GET'])
def get_trends():
    try:
        # Récupérer les paramètres de recherche
        query = request.args.get('query', '')
        duration_days = int(request.args.get('duration', 7))
        region = request.args.get('region', 'GLOBAL')
        max_results = request.args.get('max_results', 20, type=int)

        print(f"🔍 TrendSniper analyse: {query} (période: {duration_days} jours, région: {region})")

        # Calculer la date limite
        date_limit = datetime.now() - timedelta(days=duration_days)

        # Recherche YouTube avec différents ordres pour diversifier
        search_params = [
            {'order': 'relevance', 'weight': 0.4},
            {'order': 'date', 'weight': 0.3},
            {'order': 'viewCount', 'weight': 0.3}
        ]
        
        all_videos = {}
        
        for params in search_params:
            # Paramètres de base pour la recherche
            search_params_dict = {
                'q': query,
                'part': 'id,snippet',
                'maxResults': int(max_results * params['weight']) + 5,
                'type': 'video',
                'order': params['order'],
                'publishedAfter': date_limit.strftime('%Y-%m-%dT%H:%M:%SZ')
            }
            
            # Ajouter la région si elle n'est pas mondiale
            if region != 'GLOBAL':
                search_params_dict['regionCode'] = region
                
            search_response = youtube.search().list(**search_params_dict).execute()
            
            for item in search_response['items']:
                video_id = item['id']['videoId']
                if video_id not in all_videos:
                    all_videos[video_id] = item

        print(f"📊 {len(all_videos)} vidéos uniques trouvées")

        video_ids = list(all_videos.keys())[:max_results]

        if not video_ids:
            return jsonify({
                'success': True,
                'data': [],
                'message': 'Aucune vidéo trouvée pour cette recherche et période'
            })

        # Obtenir les statistiques détaillées
        videos_response = youtube.videos().list(
            part='statistics,contentDetails',
            id=','.join(video_ids)
        ).execute()

        # Combiner les résultats avec scores avancés
        results = []
        for video_item in videos_response['items']:
            video_id = video_item['id']
            if video_id in all_videos:
                search_item = all_videos[video_id]
                
                # 🎯 CALCUL DU SCORE TRENDSNIPER AVANCÉ
                score_data = calculate_trendsniper_score(search_item, video_item)
                
                if score_data['is_trending']:
                    published_at = datetime.strptime(search_item['snippet']['publishedAt'], '%Y-%m-%dT%H:%M:%SZ')
                    hours_since_published = max((datetime.now() - published_at).total_seconds() / 3600, 1)
                    views = int(video_item['statistics']['viewCount'])
                    views_per_hour = round(views / hours_since_published, 1)
                    
                    results.append({
                        'id': video_id,
                        'title': search_item['snippet']['title'],
                        'channel': search_item['snippet']['channelTitle'],
                        'thumbnail': search_item['snippet']['thumbnails']['high']['url'],
                        'publishedAt': search_item['snippet']['publishedAt'],
                        'views': views,
                        'likes': int(video_item.get('statistics', {}).get('likeCount', 0)),
                        'comments': int(video_item.get('statistics', {}).get('commentCount', 0)),
                        'duration': video_item['contentDetails']['duration'],
                        'category': query,
                        'trend_score': score_data['score'],
                        'views_per_hour': views_per_hour,
                        'hours_since_published': round(hours_since_published, 1),
                        'engagement_rate': score_data['engagement_rate'],
                        'trend_category': score_data['category']
                    })
        
        # Trier par score de tendance
        results.sort(key=lambda x: x['trend_score'], reverse=True)

        print(f"✅ {len(results)} vidéos trending détectées!")
        return jsonify({
            'success': True,
            'data': results,
            'total_analyzed': len(all_videos),
            'trending_found': len(results),
            'region': region,
            'query': query,
            'duration_days': duration_days
        })

    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        return jsonify({
            'success': False,
            'error': f"Erreur: {str(e)}"
        }), 500

def calculate_trendsniper_score(search_item, video_item):
    """
    🎯 SYSTÈME DE SCORING TRENDSNIPER AVANCÉ
    Score maximum : 100 points
    """
    
    # Données de base
    published_at = datetime.strptime(search_item['snippet']['publishedAt'], '%Y-%m-%dT%H:%M:%SZ')
    views = int(video_item['statistics']['viewCount'])
    likes = int(video_item['statistics'].get('likeCount', 0))
    comments = int(video_item['statistics'].get('commentCount', 0))
    
    # Calculs temporels
    time_since_published = datetime.now() - published_at
    hours_since_published = max(time_since_published.total_seconds() / 3600, 1)
    
    score = 0
    
    # 🕐 FRAÎCHEUR (0-35 points)
    if hours_since_published <= 6:
        freshness_score = 35
    elif hours_since_published <= 24:
        freshness_score = 30
    elif hours_since_published <= 48:
        freshness_score = 25
    elif hours_since_published <= 72:
        freshness_score = 20
    elif hours_since_published <= 168:  # 1 semaine
        freshness_score = 15
    elif hours_since_published <= 336:  # 2 semaines
        freshness_score = 10
    else:
        freshness_score = 5
    
    score += freshness_score
    
    # 🚀 VÉLOCITÉ DES VUES (0-25 points)
    views_per_hour = views / hours_since_published
    
    if views_per_hour >= 2500:
        velocity_score = 25
    elif views_per_hour >= 1000:
        velocity_score = 22
    elif views_per_hour >= 500:
        velocity_score = 18
    elif views_per_hour >= 200:
        velocity_score = 15
    elif views_per_hour >= 100:
        velocity_score = 12
    elif views_per_hour >= 50:
        velocity_score = 8
    elif views_per_hour >= 20:
        velocity_score = 5
    else:
        velocity_score = 2
    
    score += velocity_score
    
    # 💎 ENGAGEMENT (0-20 points)
    engagement_rate = (likes / max(views, 1)) * 100
    comments_rate = (comments / max(views, 1)) * 100
    
    # Score des likes
    if engagement_rate >= 5:
        likes_score = 15
    elif engagement_rate >= 3:
        likes_score = 12
    elif engagement_rate >= 2:
        likes_score = 9
    elif engagement_rate >= 1:
        likes_score = 6
    elif engagement_rate >= 0.5:
        likes_score = 3
    else:
        likes_score = 0
    
    # Score des commentaires
    if comments_rate >= 0.5:
        comments_score = 5
    elif comments_rate >= 0.2:
        comments_score = 3
    elif comments_rate >= 0.1:
        comments_score = 2
    else:
        comments_score = 1
    
    engagement_score = likes_score + comments_score
    score += engagement_score
    
    # ⚡ MOMENTUM (0-10 points)
    momentum_score = 0
    if hours_since_published <= 72:
        if views_per_hour >= 500 and engagement_rate >= 2:
            momentum_score = 10
        elif views_per_hour >= 200 and engagement_rate >= 1:
            momentum_score = 7
        elif views_per_hour >= 100:
            momentum_score = 5
        elif views_per_hour >= 50:
            momentum_score = 3
    
    score += momentum_score
    
    # 🔥 BONUS VIRAL (0-10 points)
    viral_bonus = 0
    
    if hours_since_published <= 24:
        if views >= 50000:
            viral_bonus += 5
        if views_per_hour >= 1000:
            viral_bonus += 3
        if engagement_rate >= 3:
            viral_bonus += 2
    
    if likes > 0:
        comment_like_ratio = comments / likes
        if comment_like_ratio >= 0.3:
            viral_bonus += 2
    
    viral_bonus = min(viral_bonus, 10)
    score += viral_bonus
    
    # Score final
    final_score = min(score, 100)
    
    # Statut trending
    is_trending = determine_trending_status(final_score, hours_since_published, views_per_hour)
    
    # Catégorie
    category = get_trend_category(final_score, views_per_hour)
    
    return {
        'score': final_score,
        'is_trending': is_trending,
        'engagement_rate': round(engagement_rate, 2),
        'views_per_hour': round(views_per_hour, 1),
        'category': category
    }

def determine_trending_status(score, hours_since_published, views_per_hour):
    """Détermine si une vidéo est trending"""
    if hours_since_published <= 24:
        return score >= 30 or views_per_hour >= 200
    elif hours_since_published <= 48:
        return score >= 35 or views_per_hour >= 150
    elif hours_since_published <= 72:
        return score >= 40 or views_per_hour >= 100
    elif hours_since_published <= 168:
        return score >= 50 or views_per_hour >= 80
    else:
        return score >= 60 and views_per_hour >= 50

def get_trend_category(score, views_per_hour):
    """Catégorise le type de tendance"""
    if score >= 80 or views_per_hour >= 1000:
        return 'viral'
    elif score >= 60 or views_per_hour >= 500:
        return 'trending'
    elif score >= 40 or views_per_hour >= 100:
        return 'rising'
    else:
        return 'normal'

@app.route('/api/analyze', methods=['POST'])
def analyze_video():
    try:
        data = request.json
        video_id = data.get('video_id')
        
        video_response = youtube.videos().list(
            part='snippet,statistics,contentDetails',
            id=video_id
        ).execute()
        
        if not video_response['items']:
            return jsonify({
                'status': 'error',
                'message': 'Vidéo non trouvée'
            }), 404
            
        video_item = video_response['items'][0]
        search_item = {
            'id': {'videoId': video_id},
            'snippet': video_item['snippet']
        }
        
        score_data = calculate_trendsniper_score(search_item, video_item)
        
        return jsonify({
            'status': 'success',
            'message': f'Analyse terminée pour: {video_item["snippet"]["title"]}',
            'data': {
                'video_id': video_id,
                'title': video_item['snippet']['title'],
                'channel': video_item['snippet']['channelTitle'],
                'score_data': score_data
            }
        })
    except Exception as e:
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500

# ===== ROUTES DE TÉLÉCHARGEMENT =====

def is_valid_youtube_url(url):
    """Valide si l'URL est une URL YouTube valide"""
    youtube_patterns = [
        r'(?:https?://)?(?:www\.)?youtube\.com/watch\?v=[\w-]+',
        r'(?:https?://)?(?:www\.)?youtu\.be/[\w-]+',
        r'(?:https?://)?(?:www\.)?youtube\.com/embed/[\w-]+',
        r'(?:https?://)?(?:www\.)?youtube\.com/v/[\w-]+'
    ]
    
    for pattern in youtube_patterns:
        if re.match(pattern, url):
            return True
    return False

@app.route('/api/video-info', methods=['POST'])
def get_video_info():
    """Récupère les informations d'une vidéo YouTube"""
    try:
        data = request.json
        url = data.get('url', '').strip()
        
        if not url:
            return jsonify({'success': False, 'error': 'URL manquante'}), 400
            
        if not is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'URL YouTube invalide'}), 400
        
        # Configuration yt-dlp pour récupérer les infos seulement
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            # Formats disponibles
            formats = []
            if 'formats' in info and info['formats']:
                for f in info['formats']:
                    if f.get('ext') in ['mp4', 'webm'] and f.get('height'):
                        formats.append({
                            'format_id': f['format_id'],
                            'ext': f['ext'],
                            'quality': f'{f["height"]}p',
                            'filesize': f.get('filesize', 0)
                        })
            
            # Trier par qualité (ordre décroissant)
            formats = sorted(formats, key=lambda x: int(x['quality'].replace('p', '')), reverse=True)
            
            return jsonify({
                'success': True,
                'data': {
                    'title': info.get('title', 'Titre non disponible'),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', ''),
                    'uploader': info.get('uploader', 'Inconnu'),
                    'view_count': info.get('view_count', 0),
                    'upload_date': info.get('upload_date', ''),
                    'formats': formats[:5]  # Limiter à 5 formats max
                }
            })
            
    except Exception as e:
        print(f"❌ Erreur lors de la récupération des infos: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'Erreur: {str(e)}'
        }), 500

@app.route('/api/download-video', methods=['POST'])
def download_video():
    """Télécharge une vidéo YouTube"""
    try:
        data = request.json
        url = data.get('url', '').strip()
        quality = data.get('quality', '720p')
        format_type = data.get('format', 'mp4')  # mp4 ou mp3
        
        if not url or not is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'URL YouTube invalide'}), 400
        
        # Créer un dossier temporaire unique
        temp_dir = tempfile.mkdtemp()
        
        # Configuration yt-dlp
        if format_type == 'mp3':
            ydl_opts = {
                'format': 'bestaudio/best',
                'outtmpl': f'{temp_dir}/%(title)s.%(ext)s',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                    'preferredquality': '192',
                }],
                'quiet': True,
            }
        else:
            # Vidéo MP4
            format_selector = f'best[height<={quality.replace("p", "")}][ext=mp4]'
            ydl_opts = {
                'format': format_selector,
                'outtmpl': f'{temp_dir}/%(title)s.%(ext)s',
                'quiet': True,
            }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            
            # Trouver le fichier téléchargé
            import glob
            if format_type == 'mp3':
                files = glob.glob(f'{temp_dir}/*.mp3')
            else:
                files = glob.glob(f'{temp_dir}/*.mp4')
                
            if not files:
                return jsonify({'success': False, 'error': 'Fichier non trouvé après téléchargement'}), 500
            
            file_path = files[0]
            filename = os.path.basename(file_path)
            
            return send_file(
                file_path,
                as_attachment=True,
                download_name=filename,
                mimetype='video/mp4' if format_type == 'mp4' else 'audio/mpeg'
            )
            
    except Exception as e:
        print(f"❌ Erreur lors du téléchargement: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'Erreur de téléchargement: {str(e)}'
        }), 500

@app.route('/api/download-thumbnail', methods=['POST'])
def download_thumbnail():
    """Télécharge la miniature d'une vidéo YouTube"""
    try:
        data = request.json
        url = data.get('url', '').strip()
        
        if not url or not is_valid_youtube_url(url):
            return jsonify({'success': False, 'error': 'URL YouTube invalide'}), 400
        
        # Configuration yt-dlp pour récupérer les infos
        ydl_opts = {'quiet': True, 'no_warnings': True}
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            thumbnail_url = info.get('thumbnail')
            
            if not thumbnail_url:
                return jsonify({'success': False, 'error': 'Miniature non trouvée'}), 404
            
            # Télécharger la miniature
            response = requests.get(thumbnail_url)
            if response.status_code != 200:
                return jsonify({'success': False, 'error': 'Impossible de télécharger la miniature'}), 500
            
            # Créer un fichier temporaire
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.jpg')
            temp_file.write(response.content)
            temp_file.close()
            
            # Nettoyer le titre pour le nom de fichier
            safe_title = re.sub(r'[<>:"/\\|?*]', '_', info.get('title', 'thumbnail'))
            filename = f"{safe_title}_thumbnail.jpg"
            
            return send_file(
                temp_file.name,
                as_attachment=True,
                download_name=filename,
                mimetype='image/jpeg'
            )
            
    except Exception as e:
        print(f"❌ Erreur lors du téléchargement de la miniature: {str(e)}")
        return jsonify({
            'success': False, 
            'error': f'Erreur: {str(e)}'
        }), 500

if __name__ == '__main__':
    if not YOUTUBE_API_KEY:
        print("⚠️ ATTENTION: YOUTUBE_API_KEY manquante!")
        print("💡 Créez un fichier .env avec: YOUTUBE_API_KEY=votre_cle")
    else:
        print("🚀 TrendSniper Backend lancé!")
        print(f"🔑 API Key: {YOUTUBE_API_KEY[:10]}...")
        print("🎯 Système de scoring avancé: ✅")
        print("📊 Score maximum: 100 points")
        print("🔥 Categories: Viral (80+), Trending (60+), Rising (40+)")
        print("📥 Téléchargement de vidéos: ✅")
    
    # Pour le développement local
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_ENV') == 'development'
    
    app.run(debug=debug, host='0.0.0.0', port=port) 