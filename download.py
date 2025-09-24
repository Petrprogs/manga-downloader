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
- requests

Автор: AI Assistant
"""

import sys
import re
import json
import os
import zipfile
import shutil
import requests
import time
from pathlib import Path

from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QTextEdit
from PyQt5.QtCore import QThread, pyqtSignal

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By

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

    # Константы
    COOKIE_FILE = "comx_life_cookies_v2.json"
    DOWNLOADS_DIR = "downloads"
    TEMP_DIR = "combined_cbz_temp"
    REQUEST_DELAY = 0.5  # Задержка между запросами в секундах
    
    def __init__(self):
        super().__init__()
        self.url = None
        self.cookies = None
        self.cookie_file = Path(self.COOKIE_FILE)
        self.headers = {
            "Referer": "https://comx.life/",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        }
        self._is_cancelled = False

    def run(self):
        self.cleanup()
        try:
            self.log.emit("🌐 Открытие браузера...")
            driver = self._open_browser_with_cookies()
            if driver:
                self.log.emit("🔎 Запуск отслеживания страницы манги...")
                self._auto_download_if_manga_page(driver)
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
        driver = webdriver.Chrome(options=options)

        driver.get("https://comx.life/")

        if self.cookie_file.exists():
            self.log.emit("🍪 Пробую восстановить сессию...")
            with open(self.cookie_file, "r", encoding="utf-8") as f:
                cookies = json.load(f)

            driver.delete_all_cookies()
            for c in cookies:
                c.pop("sameSite", None)
                try:
                    driver.add_cookie(c)
                except Exception as e:
                    self.log.emit(f"⚠️ Cookie {c.get('name')} не добавлен: {e}")

            driver.refresh()
            time.sleep(2)
            if driver.get_cookie("dle_user_id"):
                self.cookies = driver.get_cookies()
                self.log.emit("✅ Авторизация восстановлена!")
                return driver
            self.log.emit("⚠️ Сессия устарела, нужна новая авторизация")

        self.log.emit("🔐 Войдите вручную, я запомню cookies")
        self.log.emit("📦 Ожидание страницы манги...")

        while not driver.get_cookie("dle_user_id"):
            if self._is_cancelled:
                driver.quit()
                self.finished.emit(False)
                return None
            time.sleep(1)

        self.cookies = driver.get_cookies()
        with open(self.cookie_file, "w", encoding="utf-8") as f:
            json.dump(self.cookies, f, indent=2, ensure_ascii=False)

        return driver

    def _auto_download_if_manga_page(self, driver):
        processed_url = None

        while not self._is_cancelled:
            try:
                current_url = driver.current_url
                if current_url and current_url.endswith('/download'):
                    self.url = current_url.replace('/download', '')
                    self.log.emit(f"📍 Начинаем скачивание манги: {self.url}")
                    driver.quit()
                    self.download_manga()
                    self.finished.emit(True)
                    return

                elif current_url and "/" in current_url and ".html" in current_url and current_url != processed_url:
                    self.log.emit(f"🔍 Проверка страницы: {current_url}")
                    try:
                        btn = driver.find_element(By.CSS_SELECTOR, 'a.page__btn-track.js-follow-status')
                        driver.execute_script('''
                            arguments[0].textContent = '⬇️ Скачать';
                            arguments[0].style.backgroundColor = '#28a745';
                            arguments[0].style.color = '#fff';
                            arguments[0].style.fontWeight = 'bold';
                            arguments[0].onclick = () => { window.location.href += '/download'; };
                        ''', btn)
                        self.log.emit("✅ Кнопка заменена на 'Скачать'")
                        processed_url = current_url
                    except Exception as e:
                        self.log.emit(f"⚠️ Кнопка не найдена: {e}")

                time.sleep(0.1)

            except Exception as e:
                self.log.emit(f"❌ Ошибка: {e}")
                driver.quit()
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
        final_cbz = self._prepare_directories(manga_title)
        
        self._download_chapters(chapters, news_id)
        
        if not self._is_cancelled:
            self._create_cbz_archive(final_cbz)
        
        self.cleanup()
        if not self._is_cancelled:
            self.log.emit(f"✅ Готово: {final_cbz.resolve()}")

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
            except Exception as e:
                self.log.emit(f"❌ Не удалось загрузить cookies из файла: {e}")
                return False
        return True

    def _get_manga_data(self):
        """Получает данные манги из HTML страницы"""
        self.download_started.emit()
        self.log.emit(f"📥 Скачивание HTML: {self.url}")
        
        resp = requests.get(self.url, headers=self.headers, cookies={c['name']: c['value'] for c in self.cookies})
        html = resp.text

        match = re.search(r'window\.__DATA__\s*=\s*({.*?})\s*;', html, re.DOTALL)
        if not match:
            self.log.emit("❌ Не найден window.__DATA__")
            return None

        data = json.loads(match.group(1))
        chapters = data["chapters"][::-1]
        manga_title = data.get("title", "Manga").strip()
        
        # Извлекаем news_id из данных или URL
        news_id = data.get("news_id")
        if not news_id:
            url_match = re.search(r'/(\d+)-', self.url)
            if url_match:
                news_id = url_match.group(1)
            else:
                self.log.emit("❌ news_id не найден ни в данных, ни в URL!")
                return None
                
        return chapters, manga_title, news_id

    def _prepare_directories(self, manga_title):
        """Подготавливает директории для скачивания"""
        manga_title_safe = re.sub(r"[^\w\- ]", "_", manga_title)
        final_cbz = Path(f"{manga_title_safe}.cbz")
        
        downloads_dir = Path(self.DOWNLOADS_DIR)
        combined_dir = Path(self.TEMP_DIR)
        
        downloads_dir.mkdir(exist_ok=True)
        combined_dir.mkdir(exist_ok=True)
        
        return final_cbz

    def _download_chapters(self, chapters, news_id):
        """Скачивает все главы манги"""
        self.log.emit(f"🔢 Глав: {len(chapters)}")
        
        for i, chapter in enumerate(chapters, 1):
            if self._is_cancelled:
                self.log.emit("❌ Скачивание отменено")
                self.cleanup()
                return

            title = chapter["title"]
            chapter_id = chapter["id"]
            filename = re.sub(r"[^\w\- ]", "_", f"{i:06}_{title}") + ".zip"
            zip_path = Path(self.DOWNLOADS_DIR) / filename

            self.log.emit(f"⬇️ {i}/{len(chapters)}: {title}")
            
            if self._download_chapter(chapter_id, news_id, zip_path, title):
                self.log.emit(f"✅ Скачано: {title}")
            
            # Небольшая задержка между запросами
            time.sleep(self.REQUEST_DELAY)

    def _download_chapter(self, chapter_id, news_id, zip_path, title):
        """Скачивает одну главу манги"""
        try:
            # Подготовка запроса
            payload = f"chapter_id={chapter_id}&news_id={news_id}"
            domain = "https://com-x.life" if "com-x.life" in self.url else "https://comx.life"
            
            headers = {
                "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
                "Referer": self.url,
                "X-Requested-With": "XMLHttpRequest",
                "Origin": domain,
                "User-Agent": self.headers["User-Agent"]
            }

            cookies = {c["name"]: c["value"] for c in self.cookies}
            
            # Получаем ссылку на скачивание
            api_url = f"{domain}/engine/ajax/controller.php?mod=api&action=chapters/download"
            link_resp = requests.post(api_url, headers=headers, data=payload, cookies=cookies)
            
            if link_resp.status_code != 200:
                raise ValueError(f"Ошибка API: {link_resp.status_code}")

            json_data = link_resp.json()
            raw_url = json_data.get("data")
            if not raw_url:
                raise ValueError("Поле 'data' не найдено в JSON")

            # Скачиваем файл
            download_url = "https:" + raw_url.replace("\\/", "/")
            r = requests.get(download_url, headers=self.headers, cookies=cookies)
            
            if r.ok:
                with open(zip_path, "wb") as f:
                    f.write(r.content)
                return True
            else:
                self.log.emit(f"❌ Ошибка {r.status_code} при скачивании {title}")
                return False

        except Exception as e:
            self.log.emit(f"❌ Ошибка при обработке главы {title}: {e}")
            return False

    def _create_cbz_archive(self, final_cbz):
        """Создает CBZ архив из скачанных файлов"""
        index = 1
        self.log.emit("📦 Архивация в CBZ...")
        
        with zipfile.ZipFile(final_cbz, "w") as cbz:
            for zip_file in sorted(Path(self.DOWNLOADS_DIR).glob("*.zip")):
                if self._is_cancelled:
                    self.log.emit("❌ Архивация отменена")
                    break

                with zipfile.ZipFile(zip_file) as z:
                    for name in sorted(z.namelist()):
                        if self._is_cancelled:
                            break

                        ext = os.path.splitext(name)[1].lower()
                        out_name = f"{index:06}{ext}"
                        combined_dir = Path(self.TEMP_DIR)
                        z.extract(name, path=combined_dir)
                        os.rename(combined_dir / name, combined_dir / out_name)
                        cbz.write(combined_dir / out_name, arcname=out_name)
                        index += 1

        if self._is_cancelled and final_cbz.exists():
            try:
                final_cbz.unlink()
                self.log.emit(f"🧹 Удалён неполный архив: {final_cbz}")
            except Exception as e:
                self.log.emit(f"⚠️ Не удалось удалить архив: {e}")


class DownloaderApp(QWidget):
    """
    Главное окно приложения для скачивания манги
    
    Содержит:
    - Кнопку запуска скачивания
    - Кнопку отмены
    - Область для отображения логов
    """
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Manga Downloader")
        self.setGeometry(200, 200, 600, 400)
        layout = QVBoxLayout(self)

        self.button = QPushButton("Открыть сайт")
        self.cancel_button = QPushButton("Отмена")
        self.cancel_button.hide()
        self.logs = QTextEdit(readOnly=True)

        layout.addWidget(self.button)
        layout.addWidget(self.cancel_button)
        layout.addWidget(self.logs)

        self.button.clicked.connect(self.start_download)
        self.cancel_button.clicked.connect(self.cancel_download)

    def download_started(self):
        self.cancel_button.show()

    def start_download(self):
        self.button.setEnabled(False)
        self.logs.append("▶️ Ожидайте...")
        self.worker = MangaDownloader()
        self.worker.download_started.connect(self.download_started)
        self.worker.log.connect(self.logs.append)
        self.worker.finished.connect(self.download_finished)
        self.worker.start()

    def cancel_download(self):
        if hasattr(self, 'worker'):
            self.worker.cancel()
            self.logs.append("🛑 Отмена...")

    def download_finished(self, ok):
        self.button.setEnabled(True)
        self.cancel_button.hide()
        if (self.worker._is_cancelled):
            return
        elif ok:
            self.logs.append("✅ Скачивание завершено успешно!")
        else:
            self.logs.append("❌ Скачивание завершено с ошибкой.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    win = DownloaderApp()
    win.show()
    sys.exit(app.exec_())
