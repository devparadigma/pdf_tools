import os
import logging
import subprocess
import requests
import tempfile
from flask import Flask, request, jsonify, send_file, render_template
from werkzeug.utils import secure_filename
from PIL import Image
from datetime import datetime

# Импорты для Adobe PDF Services SDK
from adobe.pdfservices.operation.auth.service_principal_credentials import ServicePrincipalCredentials
from adobe.pdfservices.operation.exception.exceptions import ServiceApiException, ServiceUsageException, SdkException
from adobe.pdfservices.operation.io.cloud_asset import CloudAsset
from adobe.pdfservices.operation.io.stream_asset import StreamAsset
from adobe.pdfservices.operation.pdf_services import PDFServices
from adobe.pdfservices.operation.pdf_services_media_type import PDFServicesMediaType
from adobe.pdfservices.operation.pdfjobs.jobs.export_pdf_job import ExportPDFJob
from adobe.pdfservices.operation.pdfjobs.params.export_pdf.export_ocr_locale import ExportOCRLocale
from adobe.pdfservices.operation.pdfjobs.params.export_pdf.export_pdf_params import ExportPDFParams
from adobe.pdfservices.operation.pdfjobs.params.export_pdf.export_pdf_target_format import ExportPDFTargetFormat
from adobe.pdfservices.operation.pdfjobs.result.export_pdf_result import ExportPDFResult

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Создание временной директории для загрузки файлов
TEMP_DIR = tempfile.mkdtemp()
logger.info(f"Запуск приложения. Временная директория: {TEMP_DIR}")

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = TEMP_DIR
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 МБ максимальный размер файла

# Adobe PDF Services API учетные данные
PDF_SERVICES_CLIENT_ID = "YOUR_ADOBE_CLIENT_ID"
PDF_SERVICES_CLIENT_SECRET = "YOUR_ADOBE_CLIENT_SECRET"

# Функция для очистки временных файлов
def cleanup_files(*file_paths):
    for file_path in file_paths:
        if file_path and os.path.exists(file_path):
            try:
                os.remove(file_path)
                logger.info(f"Удален временный файл: {file_path}")
            except Exception as e:
                logger.error(f"Ошибка при удалении файла {file_path}: {str(e)}")

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
        
        # Получаем имя файла без расширения для результата
        output_filename = filename_base + '.docx'
        docx_path = os.path.join(app.config['UPLOAD_FOLDER'], output_filename)
        logger.info(f"Путь для сохранения результата: {docx_path}")
        
        # Чтение содержимого PDF файла
        with open(pdf_path, 'rb') as file:
            input_stream = file.read()
        
        # Настройка учетных данных Adobe PDF Services API
        credentials = ServicePrincipalCredentials(
            client_id=PDF_SERVICES_CLIENT_ID,
            client_secret=PDF_SERVICES_CLIENT_SECRET
        )
        
        # Создание экземпляра PDF Services
        pdf_services = PDFServices(credentials=credentials)
        
        # Загрузка PDF файла как ассета
        input_asset = pdf_services.upload(input_stream=input_stream, mime_type=PDFServicesMediaType.PDF)
        
        # Создание параметров для задания
        export_pdf_params = ExportPDFParams(target_format=ExportPDFTargetFormat.DOCX)
        
        # Создание нового экземпляра задания
        export_pdf_job = ExportPDFJob(input_asset=input_asset, export_pdf_params=export_pdf_params)
        
        # Отправка задания и получение результата
        location = pdf_services.submit(export_pdf_job)
        pdf_services_response = pdf_services.get_job_result(location, ExportPDFResult)
        
        # Получение содержимого из результирующего ассета
        result_asset = pdf_services_response.get_result().get_asset()
        stream_asset = pdf_services.get_content(result_asset)
        
        # Сохранение результата в файл
        with open(docx_path, "wb") as file:
            file.write(stream_asset.get_input_stream())
        
        logger.info(f"Результат сохранен по пути: {docx_path}")
        
        # Проверяем, что файл был создан
        if not os.path.exists(docx_path):
            logger.error(f"Файл не был создан по пути: {docx_path}")
            return jsonify({"error": "Ошибка при создании DOCX файла"}), 500
        
        # Отправляем файл пользователю
        logger.info(f"Отправка файла пользователю: {docx_path}")
        return send_file(
            docx_path, 
            as_attachment=True, 
            download_name=output_filename
        )
        
    except ServiceApiException as e:
        logger.error(f"Ошибка Adobe PDF Services API: {str(e)}", exc_info=True)
        return jsonify({"error": f"Ошибка API Adobe: {str(e)}"}), 500
    except ServiceUsageException as e:
        logger.error(f"Ошибка использования Adobe PDF Services: {str(e)}", exc_info=True)
        return jsonify({"error": f"Ошибка использования сервиса Adobe: {str(e)}"}), 500
    except SdkException as e:
        logger.error(f"Ошибка SDK Adobe: {str(e)}", exc_info=True)
        return jsonify({"error": f"Ошибка SDK Adobe: {str(e)}"}), 500
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
            'C:\\Program Files\\gs\\gs10.05.0\\bin\\gswin64c.exe', '-sDEVICE=pdfwrite', '-dCompatibilityLevel=1.4',
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
            logger.info("Сжатие не уменьшило размер файла, возвращаем оригинал")
            return send_file(
                pdf_path,
                as_attachment=True,
                download_name=filename_base + '_original.pdf'
            ), 200
        
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

if __name__ == '__main__':
    app.run(debug=True, port=5000)
