import os
import logging
import subprocess
import requests
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename
from PIL import Image
import convertapi

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Создание временной директории для загрузки файлов
import tempfile
TEMP_DIR = tempfile.mkdtemp()
logger.info(f"Запуск приложения. Временная директория: {TEMP_DIR}")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = TEMP_DIR
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 МБ максимальный размер файла

# Секрет для ConvertAPI
CONVERT_API_SECRET = "token_vU8NsC5l"  # Замените на ваш ключ

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/pdf-to-word', methods=['POST'])
def pdf_to_word():
    pdf_path = None
    docx_path = None
    
    try:
        logger.info("Начало обработки запроса pdf-to-word")
        logger.info(f"Содержимое request.files: {list(request.files.keys())}")
        
        if 'file' not in request.files:
            logger.error("Файл не найден в запросе")
            return jsonify({"error": "Файл не загружен"}), 400
        
        pdf_file = request.files['file']
        logger.info(f"Получен файл: {pdf_file.filename}, content_type: {pdf_file.content_type}")
        
        # Проверяем, что имя файла не пустое
        if pdf_file.filename == '':
            logger.error("Имя файла пустое")
            return jsonify({"error": "Файл не выбран"}), 400
        
        # Проверка расширения файла до применения secure_filename
        original_extension = os.path.splitext(pdf_file.filename.lower())[1]
        logger.info(f"Оригинальное расширение файла: {original_extension}")
        
        if original_extension != '.pdf':
            logger.error(f"Неверное расширение файла: {original_extension}")
            return jsonify({"error": "Файл должен быть в формате PDF"}), 400
        
        # Теперь применяем secure_filename и добавляем расширение, если оно было потеряно
        filename_base = secure_filename(os.path.splitext(pdf_file.filename)[0])
        safe_filename = filename_base + '.pdf'
        logger.info(f"Безопасное имя файла: {safe_filename}")
        
        # Сохранение загруженного PDF файла
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        pdf_file.save(pdf_path)
        logger.info(f"Файл сохранен по пути: {pdf_path}")
        
        # Проверка существования и размера файла
        if not os.path.exists(pdf_path):
            logger.error(f"Файл не был сохранен по пути: {pdf_path}")
            return jsonify({"error": "Ошибка сохранения файла"}), 500
            
        file_size = os.path.getsize(pdf_path)
        logger.info(f"Размер сохраненного файла: {file_size} байт")
        
        if file_size == 0:
            logger.error("Сохраненный файл имеет нулевой размер")
            return jsonify({"error": "Загруженный файл пуст"}), 400
        
        # Установка учетных данных API
        convertapi.api_credentials = CONVERT_API_SECRET
        logger.info("API учетные данные установлены")
        
        # Получаем имя файла без расширения для результата
        output_filename = filename_base + '.docx'
        logger.info(f"Имя выходного файла: {output_filename}")
        
        # Конвертация через API
        logger.info(f"Начало конвертации файла {pdf_path}")
        result = convertapi.convert(
            'docx', 
            {
                'File': pdf_path
            },
            from_format='pdf'
        )
        logger.info("Конвертация завершена, получен результат")
        
        # Логируем ответ API для отладки
        logger.info(f"Ответ API: {result.response}")
        
        # Определяем путь для сохранения результата
        docx_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        logger.info(f"Путь для сохранения результата: {docx_path}")
        
        # Сохраняем результат
        result.save_files(app.config['UPLOAD_FOLDER'])
        logger.info("Результат сохранен")
        
        # Проверяем, что файл был создан
        if not os.path.exists(docx_path):
            logger.warning(f"Файл не найден по пути {docx_path}, пробуем альтернативный метод")
            # Если файл не найден по ожидаемому пути, попробуем найти его по URL из ответа
            file_info = result.response['Files'][0]
            download_url = file_info['Url']
            logger.info(f"URL для скачивания: {download_url}")
            
            # Скачиваем файл по URL
            response = requests.get(download_url)
            with open(docx_path, 'wb') as f:
                f.write(response.content)
            logger.info(f"Файл скачан и сохранен по пути {docx_path}")
        
        # Отправляем файл пользователю
        logger.info(f"Отправка файла пользователю: {docx_path}")
        return send_file(
            docx_path, 
            as_attachment=True, 
            download_name=output_filename
        )
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {str(e)}", exc_info=True)
        return jsonify({"error": f"Внутренняя ошибка сервера: {str(e)}"}), 500
    finally:
        # Очистка временных файлов
        cleanup_files(pdf_path, docx_path)
        logger.info("Временные файлы очищены")

@app.route('/jpeg-to-pdf', methods=['POST'])
def jpeg_to_pdf():
    img_path = None
    pdf_path = None
    
    try:
        logger.info("Начало обработки запроса jpeg-to-pdf")
        
        if 'file' not in request.files:
            logger.error("Файл не найден в запросе")
            return jsonify({"error": "Файл не загружен"}), 400
        
        img_file = request.files['file']
        logger.info(f"Получен файл: {img_file.filename}, content_type: {img_file.content_type}")
        
        # Проверка расширения файла до применения secure_filename
        original_extension = os.path.splitext(img_file.filename.lower())[1]
        logger.info(f"Оригинальное расширение файла: {original_extension}")
        
        if original_extension not in ['.jpg', '.jpeg', '.png']:
            logger.error(f"Неверное расширение файла: {original_extension}")
            return jsonify({"error": "Файл должен быть в формате JPEG/PNG"}), 400
        
        # Применяем secure_filename и сохраняем оригинальное расширение
        filename_base = secure_filename(os.path.splitext(img_file.filename)[0])
        safe_filename = filename_base + original_extension
        logger.info(f"Безопасное имя файла: {safe_filename}")
        
        img_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], filename_base + '.pdf')
        
        logger.info(f"Сохранение изображения по пути: {img_path}")
        img_file.save(img_path)
        
        logger.info(f"Конвертация изображения в PDF: {pdf_path}")
        img = Image.open(img_path)
        img.save(pdf_path, "PDF", resolution=100.0)
        
        logger.info(f"Отправка PDF пользователю: {pdf_path}")
        return send_file(
            pdf_path, 
            as_attachment=True, 
            download_name=filename_base + '.pdf'
        )
        
    except Exception as e:
        logger.error(f"JPEG to PDF error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        # Очистка временных файлов
        cleanup_files(img_path, pdf_path)
        logger.info("Временные файлы очищены")

@app.route('/compress-pdf', methods=['POST'])
def compress_pdf():
    pdf_path = None
    compressed_path = None
    
    try:
        logger.info("Начало обработки запроса compress-pdf")
        
        if 'file' not in request.files:
            logger.error("Файл не найден в запросе")
            return jsonify({"error": "Файл не загружен"}), 400
        
        pdf_file = request.files['file']
        logger.info(f"Получен файл: {pdf_file.filename}, content_type: {pdf_file.content_type}")
        
        # Проверка расширения файла до применения secure_filename
        original_extension = os.path.splitext(pdf_file.filename.lower())[1]
        logger.info(f"Оригинальное расширение файла: {original_extension}")
        
        if original_extension != '.pdf':
            logger.error(f"Неверное расширение файла: {original_extension}")
            return jsonify({"error": "Файл должен быть в формате PDF"}), 400
        
        # Применяем secure_filename и сохраняем оригинальное расширение
        filename_base = secure_filename(os.path.splitext(pdf_file.filename)[0])
        safe_filename = filename_base + '.pdf'
        logger.info(f"Безопасное имя файла: {safe_filename}")
        
        pdf_path = os.path.join(app.config['UPLOAD_FOLDER'], safe_filename)
        compressed_path = os.path.join(app.config['UPLOAD_FOLDER'], filename_base + '_compressed.pdf')
        
        logger.info(f"Сохранение PDF по пути: {pdf_path}")
        pdf_file.save(pdf_path)
        
        # Используем ghostscript для сжатия
        logger.info("Запуск Ghostscript для сжатия PDF")
        gs_command = [
            'gs', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
            '-dPDFSETTINGS=/ebook', '-dNOPAUSE', '-dBATCH', '-dQUIET',
            '-dDownsampleColorImages=true', '-dColorImageResolution=72',
            '-dRemoveUnusedObjects=true',
            f'-sOutputFile={compressed_path}', pdf_path
        ]

        subprocess.run(gs_command, check=True)
        logger.info("Ghostscript завершил работу")
        
        # Проверяем, действительно ли файл стал меньше
        original_size = os.path.getsize(pdf_path)
        compressed_size = os.path.getsize(compressed_path)
        logger.info(f"Размер оригинала: {original_size} байт, размер сжатого: {compressed_size} байт")
        
        if compressed_size >= original_size:
            # Если сжатие не дало результата, возвращаем оригинал с предупреждением
            logger.info("Сжатие не дало результата, возвращаем оригинал")
            cleanup_files(compressed_path)
            return jsonify({
                "warning": "Файл не удалось сжать дальше. Возвращен оригинал.",
                "original_size": original_size,
                "compressed_size": original_size
            }), 200
        
        logger.info(f"Отправка сжатого PDF пользователю: {compressed_path}")
        return send_file(
            compressed_path, 
            as_attachment=True, 
            download_name=filename_base + '_compressed.pdf'
        )
        
    except Exception as e:
        logger.error(f"Compress PDF error: {str(e)}", exc_info=True)
        return jsonify({"error": str(e)}), 500
    finally:
        # Очистка временных файлов
        cleanup_files(pdf_path, compressed_path)
        logger.info("Временные файлы очищены")

def cleanup_files(*files):
    """Удаляет временные файлы, если они существуют"""
    for file_path in files:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Удален файл: {file_path}")
            except Exception as e:
                logger.error(f"Ошибка при удалении файла {file_path}: {str(e)}")

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True)
