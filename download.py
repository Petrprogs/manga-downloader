"""
Manga Downloader - Автоматический скачиватель манги с com-x.life

Этот скрипт автоматически:
1. Открывает браузер и авторизуется на сайте
2. Отслеживает страницы манги
3. Скачивает все главы в формате ZIP
4. Объединяет их в единый CBZ файл

Требования:
- Python 3.7+
- PyQt5
- Selenium
- Chrome браузер
- curl_cffi
- cloudscraper
- requests

Автор: AI Assistant
"""

import sys
import re
import json
import os
import zipfile
import shutil
import curl_cffi
import time
import cloudscraper
from pathlib import Path

from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QTextEdit, QLabel, QSpinBox, 
                             QGroupBox, QRadioButton)
from PyQt5.QtCore import QThread, pyqtSignal

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


class ChapterDownloader:
    """Класс для скачивания глав с тремя уровнями fallback"""
    
    def __init__(self, logger, cookies, referer_url):
        self.logger = logger
        self.cookies = cookies
        self.referer_url = referer_url
        self.session = None
        self.scraper = None
        self.driver = None
        
    def log_message(self, msg):
        """Отправляет сообщение в лог через сигнал родительского класса"""
        if hasattr(self.logger, 'log') and hasattr(self.logger.log, 'emit'):
            self.logger.log.emit(msg)
        else:
            print(msg)
    
    def method1_curl_cffi(self, chapter_id, news_id, zip_path, title):
        """Метод 1: Использование curl_cffi с полной эмуляцией браузера"""
        try:
            self.log_message(f"  🔄 Метод 1 (curl_cffi) для {title}...")
            
            if not self.session:
                self.session = curl_cffi.Session()
                self.session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": "https://com-x.life",
                    "Referer": self.referer_url,
                })
                
                for cookie in self.cookies:
                    self.session.cookies.set(cookie['name'], cookie['value'])
            
            api_url = "https://com-x.life/engine/ajax/controller.php?mod=api&action=chapters/download"
            payload = f"chapter_id={chapter_id}&news_id={news_id}"
            
            response = self.session.post(api_url, data=payload, impersonate="chrome")
            
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")
            
            json_data = response.json()
            raw_url = json_data.get("data")
            if not raw_url:
                raise Exception("Нет URL в ответе")
            
            download_url = raw_url.replace("\\/", "/")
            if download_url.startswith("//"):
                download_url = "https:" + download_url
            
            file_response = self.session.get(download_url, impersonate="chrome", allow_redirects=True)
            
            if file_response.status_code == 200:
                with open(zip_path, "wb") as f:
                    f.write(file_response.content)
                
                if zipfile.is_zipfile(zip_path):
                    size = os.path.getsize(zip_path) / 1024
                    self.log_message(f"  ✅ Метод 1 успешен ({size:.1f} KB)")
                    return True
                else:
                    raise Exception("Не ZIP архив")
            
            raise Exception(f"Ошибка скачивания: {file_response.status_code}")
            
        except Exception as e:
            self.log_message(f"  ⚠️ Метод 1 не сработал: {str(e)[:100]}")
            return False
    
    def method2_cloudscraper(self, chapter_id, news_id, zip_path, title):
        """Метод 2: Использование cloudscraper для обхода Cloudflare"""
        try:
            self.log_message(f"  🔄 Метод 2 (cloudscraper) для {title}...")
            
            if not self.scraper:
                self.scraper = cloudscraper.create_scraper(
                    browser={
                        'browser': 'chrome',
                        'platform': 'windows',
                        'desktop': True,
                        'mobile': False
                    }
                )
                
                self.scraper.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                    "Accept": "application/json, text/javascript, */*; q=0.01",
                    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                    "X-Requested-With": "XMLHttpRequest",
                    "Origin": "https://com-x.life",
                    "Referer": self.referer_url,
                })
                
                cookies_dict = {c['name']: c['value'] for c in self.cookies}
                self.scraper.cookies.update(cookies_dict)
            
            api_url = "https://com-x.life/engine/ajax/controller.php?mod=api&action=chapters/download"
            payload = {"chapter_id": chapter_id, "news_id": news_id}
            
            response = self.scraper.post(api_url, data=payload, timeout=30)
            
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")
            
            json_data = response.json()
            raw_url = json_data.get("data")
            if not raw_url:
                raise Exception("Нет URL в ответе")
            
            download_url = raw_url.replace("\\/", "/")
            if download_url.startswith("//"):
                download_url = "https:" + download_url
            
            file_response = self.scraper.get(
                download_url, 
                timeout=60,
                allow_redirects=True,
                headers={
                    "Referer": self.referer_url,
                    "Accept": "application/zip,*/*"
                }
            )
            
            if file_response.status_code == 200:
                with open(zip_path, "wb") as f:
                    f.write(file_response.content)
                
                if zipfile.is_zipfile(zip_path):
                    size = os.path.getsize(zip_path) / 1024
                    self.log_message(f"  ✅ Метод 2 успешен ({size:.1f} KB)")
                    return True
                else:
                    raise Exception("Не ZIP архив")
            
            raise Exception(f"Ошибка скачивания: {file_response.status_code}")
            
        except Exception as e:
            self.log_message(f"  ⚠️ Метод 2 не сработал: {str(e)[:100]}")
            return False
   
    def method3_selenium_recovery(self, chapter_id, news_id, zip_path, title):
        """Метод 3: Восстановление сессии через Selenium при 403 ошибке"""
        driver = None
        try:
            self.log_message(f"  🔄 Метод 3 (Selenium recovery) для {title}...")
            
            options = Options()
            options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
            options.add_experimental_option("detach", False)
            
            driver = webdriver.Chrome(options=options)
            
            driver.get("https://com-x.life")
            
            for cookie in self.cookies:
                try:
                    cookie_dict = {
                        'name': cookie['name'],
                        'value': cookie['value'],
                        'domain': '.com-x.life'
                    }
                    driver.add_cookie(cookie_dict)
                except:
                    pass
            
            driver.refresh()
            time.sleep(2)
            
            updated_cookies = driver.get_cookies()
            self.cookies = updated_cookies
            
            self.log_message(f"  🔄 Повторная попытка с обновленными куками...")
            
            if self.session:
                self.session.close()
            self.session = curl_cffi.Session()
            self.session.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/javascript, */*; q=0.01",
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "X-Requested-With": "XMLHttpRequest",
                "Origin": "https://com-x.life",
                "Referer": self.referer_url,
            })
            
            for cookie in updated_cookies:
                self.session.cookies.set(cookie['name'], cookie['value'])
            
            api_url = "https://com-x.life/engine/ajax/controller.php?mod=api&action=chapters/download"
            payload = f"chapter_id={chapter_id}&news_id={news_id}"
            
            response = self.session.post(api_url, data=payload, impersonate="chrome")
            
            if response.status_code != 200:
                raise Exception(f"HTTP {response.status_code}")
            
            json_data = response.json()
            raw_url = json_data.get("data")
            if not raw_url:
                raise Exception("Нет URL в ответе")
            
            download_url = raw_url.replace("\\/", "/")
            if download_url.startswith("//"):
                download_url = "https:" + download_url
            
            file_response = self.session.get(download_url, impersonate="chrome", allow_redirects=True)
            
            if file_response.status_code == 200:
                with open(zip_path, "wb") as f:
                    f.write(file_response.content)
                
                if zipfile.is_zipfile(zip_path):
                    size = os.path.getsize(zip_path) / 1024
                    self.log_message(f"  ✅ Метод 3 успешен ({size:.1f} KB)")
                    
                    try:
                        important_cookies = []
                        for c in updated_cookies:
                            important_cookies.append(c)
                        
                        cookie_file = Path("comx_life_cookies_v3.json")
                        with open(cookie_file, "w", encoding="utf-8") as f:
                            json.dump(important_cookies, f, indent=2, ensure_ascii=False)
                        self.log_message(f"  💾 Обновленные куки сохранены")
                    except Exception as e:
                        self.log_message(f"  ⚠️ Не удалось сохранить куки: {e}")
                    
                    return True
                else:
                    raise Exception("Не ZIP архив")
            
            raise Exception(f"Ошибка скачивания: {file_response.status_code}")
            
        except Exception as e:
            self.log_message(f"  ⚠️ Метод 3 не сработал: {str(e)[:100]}")
            return False
        finally:
            if driver:
                driver.quit()

    def download_with_fallback(self, chapter_id, news_id, zip_path, title):
        """Пробует все методы по очереди"""
        
        if self.method1_curl_cffi(chapter_id, news_id, zip_path, title):
            return True
        
        time.sleep(1)
        
        if self.method2_cloudscraper(chapter_id, news_id, zip_path, title):
            return True
        
        time.sleep(1)
        
        if self.method3_selenium_recovery(chapter_id, news_id, zip_path, title):
            return True
        
        self.log_message(f"  ❌ Все методы не сработали для {title}")
        return False


class MangaDownloader(QThread):
    """
    Класс для автоматического скачивания манги с сайта com-x.life
    
    Функциональность:
    - Автоматическое открытие браузера и авторизация
    - Отслеживание страниц манги
    - Скачивание всех глав в формате ZIP
    - Объединение в единый CBZ файл
    """
    log = pyqtSignal(str)
    finished = pyqtSignal(bool)
    download_started = pyqtSignal()
    chapters_found = pyqtSignal(int, str, str)
    range_updated = pyqtSignal(int, int)

    COOKIE_FILE = "comx_life_cookies_v3.json"
    DOWNLOADS_DIR = "downloads"
    TEMP_DIR = "combined_cbz_temp"
    REQUEST_DELAY = 1.5
    
    def __init__(self):
        super().__init__()
        self.url = None
        self.cookies = None
        self.cookie_file = Path(self.COOKIE_FILE)
        self._is_cancelled = False
        self.failed_chapters = []
        self.chapter_range = None
        self.driver = None
        self.manga_title = None
        self.total_chapters = 0

    def set_chapter_range(self, start=None, end=None):
        """Устанавливает диапазон глав для скачивания"""
        if start is not None and end is not None:
            self.chapter_range = (start, end)
            self.log.emit(f"📊 Установлен диапазон глав: {start}-{end}")
        else:
            self.chapter_range = None
            self.log.emit("📊 Установлено скачивание всех глав")

    def run(self):
        self.cleanup()
        try:
            self.log.emit("🌐 Открытие браузера...")
            self.driver = self._open_browser_with_cookies()
            if self.driver:
                self.log.emit("🔎 Запуск отслеживания страницы манги...")
                self._monitor_manga_pages()
        except Exception as e:
            self.log.emit(f"❌ Ошибка: {e}")
            self.finished.emit(False)

    def cancel(self):
        self._is_cancelled = True

    def cleanup(self):
        for dir_name in [self.DOWNLOADS_DIR, self.TEMP_DIR]:
            dir_path = Path(dir_name)
            if dir_path.exists():
                shutil.rmtree(dir_path)
                self.log.emit(f"🧹 Очищено: {dir_name}")

    def _open_browser_with_cookies(self):
        options = Options()
        options.add_experimental_option("detach", True)
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        driver = webdriver.Chrome(options=options)

        driver.get("https://com-x.life")

        if self.cookie_file.exists():
            self.log.emit("🍪 Пробую восстановить сессию...")
            with open(self.cookie_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            driver.delete_all_cookies()
            for c in cookies:
                c.pop("sameSite", None)
                c.pop("secure", None)
                c.pop("httpOnly", None)
                try:
                    driver.add_cookie(c)
                except Exception as e:
                    self.log.emit(f"⚠️ Cookie {c.get('name')} не добавлен: {e}")

            driver.refresh()
            time.sleep(3)
            
            if driver.get_cookie("dle_user_id") and driver.get_cookie("dle_password"):
                self.cookies = driver.get_cookies()
                self.log.emit("✅ Авторизация восстановлена!")
                return driver
            self.log.emit("⚠️ Сессия устарела, нужна новая авторизация")

        self.log.emit("🔐 Войдите вручную, я запомню cookies")
        self.log.emit("📦 Ожидание страницы манги...")

        while not (driver.get_cookie("dle_user_id") and driver.get_cookie("dle_password")):
            if self._is_cancelled:
                driver.quit()
                self.finished.emit(False)
                return None
            time.sleep(1)

        self.cookies = driver.get_cookies()
        important_cookies = []
        for c in self.cookies:
            if c['name'] in ['dle_user_id', 'dle_password', 'dle_hash', 'PHPSESSID']:
                important_cookies.append(c)
        
        with open(self.cookie_file, "w", encoding="utf-8") as f:
            json.dump(important_cookies, f, indent=2, ensure_ascii=False)

        return driver

    def _get_manga_data_from_url(self, url):
        """Получает данные манги из URL без скачивания"""
        try:
            with curl_cffi.Session() as session:
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                })
                
                for cookie in self.cookies:
                    session.cookies.set(cookie['name'], cookie['value'])
                
                resp = session.get(url, impersonate="chrome")
                html = resp.text

            match = re.search(r'window\.__DATA__\s*=\s*({.*?})\s*;', html, re.DOTALL)
            if not match:
                return None

            data = json.loads(match.group(1))
            chapters = data["chapters"][::-1]
            manga_title = data.get("title", "Manga").strip()
            
            self.total_chapters = len(chapters)
            self.manga_title = manga_title
            
            return self.total_chapters, manga_title
            
        except Exception as e:
            self.log.emit(f"⚠️ Ошибка при получении данных манги: {e}")
            return None

    def _monitor_manga_pages(self):
        """Отслеживает переходы на страницы манги и обновляет информацию о главах"""
        processed_urls = set()
        wait = WebDriverWait(self.driver, 10)

        while not self._is_cancelled:
            try:
                current_url = self.driver.current_url
                
                if current_url and current_url.endswith('/download'):
                    self.url = current_url.replace('/download', '')
                    self.log.emit(f"📍 Начинаем скачивание манги: {self.url}")
                    
                    if self.chapter_range:
                        self.range_updated.emit(self.chapter_range[0], self.chapter_range[1])
                    
                    self.driver.quit()
                    self.download_manga()
                    self.finished.emit(True)
                    return

                elif current_url and "/" in current_url and ".html" in current_url:
                    if current_url not in processed_urls:
                        self.log.emit(f"🔍 Обнаружена страница манги: {current_url}")
                        
                        manga_data = self._get_manga_data_from_url(current_url)
                        if manga_data:
                            total_chapters, manga_title = manga_data
                            self.log.emit(f"📊 Найдено глав: {total_chapters}")
                            self.chapters_found.emit(total_chapters, manga_title, current_url)
                            processed_urls.add(current_url)
                        
                        try:
                            btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'a.page__btn-track.js-follow-status')))
                            
                            self.driver.execute_script('''
                                arguments[0].textContent = '⬇️ Скачать';
                                arguments[0].style.backgroundColor = '#28a745';
                                arguments[0].style.color = '#fff';
                                arguments[0].style.fontWeight = 'bold';
                                arguments[0].style.padding = '10px 20px';
                                arguments[0].style.borderRadius = '5px';
                                arguments[0].style.cursor = 'pointer';
                                arguments[0].onclick = function() { 
                                    window.location.href = window.location.href + '/download'; 
                                };
                            ''', btn)
                            self.log.emit("✅ Кнопка заменена на 'Скачать'")
                        except Exception as e:
                            self.log.emit(f"⚠️ Кнопка не найдена: {e}")

                time.sleep(0.5)

            except Exception as e:
                self.log.emit(f"❌ Ошибка: {e}")
                self.driver.quit()
                self.finished.emit(False)
                return

    def download_manga(self):
        """Основной метод скачивания манги"""
        if not self._load_cookies():
            return
            
        manga_data = self._get_manga_data()
        if not manga_data:
            return
            
        chapters, manga_title, news_id = manga_data
        
        if self.chapter_range:
            start, end = self.chapter_range
            start_idx = max(0, start - 1)
            end_idx = min(len(chapters), end)
            chapters = chapters[start_idx:end_idx]
            self.log.emit(f"📊 Выбран диапазон глав: {start}-{end} (всего {len(chapters)} глав)")
        else:
            self.log.emit(f"📊 Выбраны все главы (всего {len(chapters)} глав)")
        
        final_cbz = self._prepare_directories(manga_title)
        
        chapter_downloader = ChapterDownloader(self, self.cookies, self.url)
        
        self.failed_chapters = []
        
        self._download_chapters(chapters, news_id, chapter_downloader)
        
        if self.failed_chapters and not self._is_cancelled:
            self.log.emit(f"\n⚠️ Не удалось скачать {len(self.failed_chapters)} глав:")
            for ch in self.failed_chapters:
                self.log.emit(f"  • {ch}")
            self.log.emit("")
        
        if not self._is_cancelled:
            if self.failed_chapters:
                self.log.emit("⚠️ Некоторые главы не удалось скачать, но архив будет создан из успешных")
            
            self._create_cbz_archive(final_cbz)
        
        self.cleanup()
        if not self._is_cancelled:
            if self.failed_chapters:
                self.log.emit(f"\n⚠️ Частично завершено. Пропущено глав: {len(self.failed_chapters)}")
                self.log.emit(f"📦 Архив создан: {final_cbz.resolve()} (без пропущенных глав)")
            else:
                self.log.emit(f"\n✅ Полностью готово: {final_cbz.resolve()}")

    def _load_cookies(self):
        """Загружает cookies из файла если они не заданы"""
        if not self.cookies:
            self.log.emit("⚠️ Предупреждение: cookies не заданы — загружаю из файла")
            try:
                with open(self.cookie_file, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                    self.cookies = raw if isinstance(raw, list) else [
                        {"name": k, "value": v} for k, v in raw.items()
                    ]
                self.log.emit(f"✅ Загружено {len(self.cookies)} cookies из файла")
            except Exception as e:
                self.log.emit(f"❌ Не удалось загрузить cookies из файла: {e}")
                return False
        return True

    def _get_manga_data(self):
        """Получает данные манги из HTML страницы"""
        self.download_started.emit()
        self.log.emit(f"📥 Скачивание HTML: {self.url}")
        
        try:
            with curl_cffi.Session() as session:
                session.headers.update({
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                })
                
                for cookie in self.cookies:
                    session.cookies.set(cookie['name'], cookie['value'])
                
                resp = session.get(self.url, impersonate="chrome")
                html = resp.text

            match = re.search(r'window\.__DATA__\s*=\s*({.*?})\s*;', html, re.DOTALL)
            if not match:
                self.log.emit("❌ Не найден window.__DATA__")
                return None

            data = json.loads(match.group(1))
            chapters = data["chapters"][::-1]
            manga_title = data.get("title", "Manga").strip()
            
            news_id = data.get("news_id")
            if not news_id:
                url_match = re.search(r'/(\d+)-', self.url)
                if url_match:
                    news_id = url_match.group(1)
                else:
                    self.log.emit("❌ news_id не найден ни в данных, ни в URL!")
                    return None
                    
            self.log.emit(f"📊 Название: {manga_title}")
            self.log.emit(f"📊 ID манги: {news_id}")
            self.log.emit(f"📊 Всего глав: {len(chapters)}")
            
            return chapters, manga_title, news_id
            
        except Exception as e:
            self.log.emit(f"❌ Ошибка при получении данных манги: {e}")
            return None

    def _prepare_directories(self, manga_title):
        """Подготавливает директории для скачивания"""
        manga_title_safe = re.sub(r"[^\w\- ]", "_", manga_title)
        final_cbz = Path(f"{manga_title_safe}.cbz")
        
        downloads_dir = Path(self.DOWNLOADS_DIR)
        combined_dir = Path(self.TEMP_DIR)
        
        downloads_dir.mkdir(exist_ok=True)
        combined_dir.mkdir(exist_ok=True)
        
        return final_cbz

    def _download_chapters(self, chapters, news_id, chapter_downloader):
        """Скачивает все главы манги с использованием fallback методов"""
        self.log.emit(f"\n🔢 Начинаем скачивание {len(chapters)} глав...")
        self.log.emit("📡 Используются методы: curl_cffi → cloudscraper\n")
        
        for i, chapter in enumerate(chapters, 1):
            if self._is_cancelled:
                self.log.emit("❌ Скачивание отменено")
                return

            title = chapter["title"]
            chapter_id = chapter["id"]
            filename = re.sub(r"[^\w\- ]", "_", f"{i:04}_{title}") + ".zip"
            zip_path = Path(self.DOWNLOADS_DIR) / filename

            self.log.emit(f"📖 Глава {i}/{len(chapters)}: {title}")
            self.log.emit(f"   ID: {chapter_id}")
            
            success = chapter_downloader.download_with_fallback(
                chapter_id, news_id, zip_path, title
            )
            
            if success:
                self.log.emit(f"  ✅ Успешно\n")
            else:
                self.failed_chapters.append(f"Глава {i}: {title}")
                self.log.emit(f"  ❌ Не удалось скачать\n")
            
            time.sleep(self.REQUEST_DELAY)

    def _create_cbz_archive(self, final_cbz):
        """Создает CBZ архив из скачанных файлов"""
        index = 1
        self.log.emit("📦 Архивация в CBZ...")
        
        zip_files = sorted(Path(self.DOWNLOADS_DIR).glob("*.zip"))
        
        if not zip_files:
            self.log.emit("❌ Нет файлов для архивации")
            return
        
        successful_files = 0
        total_pages = 0
        
        try:
            with zipfile.ZipFile(final_cbz, "w", zipfile.ZIP_DEFLATED) as cbz:
                for zip_file in zip_files:
                    if self._is_cancelled:
                        self.log.emit("❌ Архивация отменена")
                        break

                    self.log.emit(f"📦 Обработка: {zip_file.name}")
                    
                    try:
                        with zipfile.ZipFile(zip_file, 'r') as z:
                            file_list = sorted(z.namelist())
                            chapter_pages = 0
                            
                            for name in file_list:
                                if self._is_cancelled:
                                    break

                                ext = os.path.splitext(name)[1].lower()
                                if ext not in ['.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp']:
                                    continue
                                
                                out_name = f"{index:06}{ext}"
                                
                                combined_dir = Path(self.TEMP_DIR)
                                z.extract(name, path=combined_dir)
                                
                                src = combined_dir / name
                                dst = combined_dir / out_name
                                
                                if src.exists():
                                    src.rename(dst)
                                    cbz.write(dst, arcname=out_name)
                                    index += 1
                                    chapter_pages += 1
                            
                            self.log.emit(f"  📄 Страниц в главе: {chapter_pages}")
                            successful_files += 1
                            total_pages += chapter_pages
                    
                    except Exception as e:
                        self.log.emit(f"  ⚠️ Ошибка при обработке {zip_file.name}: {e}")
                        continue
            
            self.log.emit(f"\n📊 Статистика:")
            self.log.emit(f"  • Всего страниц: {total_pages}")
            self.log.emit(f"  • Успешно обработано глав: {successful_files}/{len(zip_files)}")
            
            if successful_files == 0:
                self.log.emit("❌ Не удалось обработать ни одной главы")
                if final_cbz.exists():
                    final_cbz.unlink()
                return
            
        except Exception as e:
            self.log.emit(f"❌ Ошибка при создании CBZ: {e}")
            if final_cbz.exists():
                final_cbz.unlink()


class DownloaderApp(QWidget):
    """
    Главное окно приложения для скачивания манги
    
    Содержит:
    - Кнопку запуска скачивания
    - Кнопку отмены
    - Элементы выбора диапазона глав
    - Область для отображения логов
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Manga Downloader")
        self.setGeometry(200, 200, 800, 650)
        
        main_layout = QVBoxLayout(self)
        
        button_layout = QHBoxLayout()
        self.button = QPushButton("🚀 Открыть сайт и начать")
        self.cancel_button = QPushButton("⏹️ Отмена")
        self.cancel_button.hide()
        button_layout.addWidget(self.button)
        button_layout.addWidget(self.cancel_button)
        button_layout.addStretch()
        
        range_group = QGroupBox("Выбор глав")
        range_layout = QVBoxLayout()
        
        self.radio_all = QRadioButton("Все главы")
        self.radio_all.setChecked(True)
        self.radio_range = QRadioButton("Диапазон глав:")
        
        range_mode_layout = QHBoxLayout()
        range_mode_layout.addWidget(self.radio_all)
        range_mode_layout.addWidget(self.radio_range)
        range_mode_layout.addStretch()
        
        range_input_layout = QHBoxLayout()
        range_input_layout.addSpacing(30)
        
        self.label_start = QLabel("С:")
        self.spin_start = QSpinBox()
        self.spin_start.setMinimum(1)
        self.spin_start.setMaximum(9999)
        self.spin_start.setValue(1)
        self.spin_start.setEnabled(False)
        
        self.label_end = QLabel("По:")
        self.spin_end = QSpinBox()
        self.spin_end.setMinimum(1)
        self.spin_end.setMaximum(9999)
        self.spin_end.setValue(10)
        self.spin_end.setEnabled(False)
        
        self.label_info = QLabel("(перейдите на страницу манги для загрузки информации)")
        self.label_info.setStyleSheet("color: gray;")
        
        range_input_layout.addWidget(self.label_start)
        range_input_layout.addWidget(self.spin_start)
        range_input_layout.addWidget(self.label_end)
        range_input_layout.addWidget(self.spin_end)
        range_input_layout.addWidget(self.label_info)
        range_input_layout.addStretch()
        
        range_layout.addLayout(range_mode_layout)
        range_layout.addLayout(range_input_layout)
        range_group.setLayout(range_layout)
        
        self.logs = QTextEdit(readOnly=True)
        self.logs.setStyleSheet("""
            QTextEdit {
                font-family: Consolas, Monospace;
                font-size: 10pt;
                background-color: #1e1e1e;
                color: #d4d4d4;
            }
        """)

        main_layout.addLayout(button_layout)
        main_layout.addWidget(range_group)
        main_layout.addWidget(self.logs)

        self.button.clicked.connect(self.start_download)
        self.cancel_button.clicked.connect(self.cancel_download)
        self.radio_all.toggled.connect(self._on_range_mode_changed)
        self.radio_range.toggled.connect(self._on_range_mode_changed)
        self.spin_start.valueChanged.connect(self._on_range_changed)
        self.spin_end.valueChanged.connect(self._on_range_changed)

        self.current_manga_url = None
        self.worker = None

    def _on_range_mode_changed(self):
        """Обработчик изменения режима выбора глав"""
        is_range = self.radio_range.isChecked()
        self.spin_start.setEnabled(is_range)
        self.spin_end.setEnabled(is_range)
        
        if self.worker and is_range:
            self.worker.set_chapter_range(self.spin_start.value(), self.spin_end.value())
        elif self.worker and not is_range:
            self.worker.set_chapter_range()
    
    def _on_range_changed(self):
        """Обработчик изменения значений спиннеров"""
        if self.worker and self.radio_range.isChecked():
            self.worker.set_chapter_range(self.spin_start.value(), self.spin_end.value())
        
    def _update_chapter_info(self, total_chapters, manga_title, manga_url):
        """Обновляет информацию о количестве глав после обнаружения страницы манги"""
        self.current_manga_url = manga_url
        self.label_info.setText(f"(всего глав: {total_chapters})")
        self.spin_start.setMaximum(total_chapters)
        self.spin_end.setMaximum(total_chapters)
        self.spin_end.setValue(total_chapters)
        self.logs.append(f"📊 Загружена информация о манге \"{manga_title}\": {total_chapters} глав")
        
        if self.worker and self.radio_range.isChecked():
            self.worker.set_chapter_range(self.spin_start.value(), self.spin_end.value())

    def _update_range_from_worker(self, start, end):
        """Обновляет диапазон в GUI из worker (при начале скачивания)"""
        self.spin_start.setValue(start)
        self.spin_end.setValue(end)
        self.radio_range.setChecked(True)
        self.logs.append(f"📊 Используется сохраненный диапазон глав: {start}-{end}")

    def download_started(self):
        self.cancel_button.show()
        self.logs.append("")

    def start_download(self):
        self.button.setEnabled(False)
        self.logs.append("▶️ Запуск Manga Downloader")
        self.logs.append("📡 Методы: curl_cffi → cloudscraper")
        
        self.worker = MangaDownloader()
        
        self.worker.download_started.connect(self.download_started)
        self.worker.log.connect(self.logs.append)
        self.worker.finished.connect(self.download_finished)
        self.worker.chapters_found.connect(self._update_chapter_info)
        self.worker.range_updated.connect(self._update_range_from_worker)
        
        if self.radio_range.isChecked():
            self.worker.set_chapter_range(self.spin_start.value(), self.spin_end.value())
        
        self.worker.start()

    def cancel_download(self):
        if self.worker:
            self.worker.cancel()
            self.logs.append("🛑 Отмена...")

    def download_finished(self, ok):
        self.button.setEnabled(True)
        self.cancel_button.hide()
        
        if self.worker and self.worker._is_cancelled:
            self.logs.append("⏹️ Скачивание завершено пользователем.")
        elif ok:
            if self.worker and self.worker.failed_chapters:
                self.logs.append(f"\n⚠️ Завершено с пропусками ({len(self.worker.failed_chapters)} глав не скачано)")
            else:
                self.logs.append("\n✅ Скачивание полностью успешно!")
        else:
            self.logs.append("\n❌ Скачивание завершено с критической ошибкой.")
        
        self.worker = None


if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = DownloaderApp()
    win.show()
    sys.exit(app.exec_())