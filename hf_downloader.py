# -*- coding: utf-8 -*-
"""
高级 Hugging Face 下载器
支持详细进度显示、进度保存和断点续传
支持通过 hf-mirror.com 镜像站加速下载（国内用户推荐）

pyinstaller --onefile -w --name "hf_downloader" hf_downloader.py

镜像站说明：
- hf-mirror.com 是 Hugging Face 的国内镜像站
- 可以为国内用户提供更快的下载速度
- 镜像站由公益组织维护，感谢其贡献
"""

# 修复Windows下的Unicode编码问题
import sys
import os

# 设置环境变量强制使用UTF-8
os.environ['PYTHONIOENCODING'] = 'utf-8'

# 重新配置stdout和stderr的编码
if sys.platform.startswith('win'):
    import codecs
    
    # 尝试设置控制台编码为UTF-8
    try:
        # 设置默认编码
        try:
            if hasattr(sys.stdout, 'reconfigure'):
                sys.stdout.reconfigure(encoding='utf-8', errors='replace')
                sys.stderr.reconfigure(encoding='utf-8', errors='replace')
            else:
                # 对于较老的Python版本
                sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
                sys.stderr = codecs.getwriter('utf-8')(sys.stderr.buffer)
        except AttributeError:
            pass
            sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
    except Exception:
        # 如果重配置失败，使用安全的输出函数
        pass

# 保存原始的print函数
original_print = print

# 安全的打印函数，处理编码错误
def safe_print(*args, **kwargs):
    """安全的打印函数，避免编码错误"""
    try:
        original_print(*args, **kwargs)  # 使用原始的print函数
    except UnicodeEncodeError:
        # 移除emoji字符后重试
        safe_args = []
        for arg in args:
            if isinstance(arg, str):
                # 替换常见的emoji
                replacements = {
                    '🎯': '[目标]',
                    '📁': '[目录]',
                    '🔧': '[设置]',
                    '📄': '[文件]',
                    '📥': '[包含]',
                    '🚫': '[排除]',
                    '✅': '[成功]',
                    '❌': '[失败]',
                    '💾': '[保存]',
                    '🔗': '[链接]',
                    '🔑': '[令牌]',
                    '📋': '[任务]',
                    '🆕': '[新增]',
                    '🎉': '[完成]',
                    '⚠️': '[警告]',
                    '⏹️': '[停止]',
                    '💡': '[提示]',
                    '📊': '[统计]',
                    '⏱️': '[时间]',
                    '📦': '[大小]',
                    '⏰': '[剩余]',
                    '🚀': '[开始]',
                    '🔍': '[搜索]'
                }
                safe_arg = str(arg)
                for emoji, replacement in replacements.items():
                    safe_arg = safe_arg.replace(emoji, replacement)
                safe_args.append(safe_arg)
            else:
                safe_args.append(str(arg))
        original_print(*safe_args, **kwargs)  # 使用原始的print函数

# 替换内置的print函数
print = safe_print

import os
import json
import time
import threading
import ctypes
import sys
from pathlib import Path
from typing import Optional, List, Dict, Any
import logging
from datetime import datetime

try:
    from huggingface_hub import hf_hub_download, list_repo_files, HfApi
    from huggingface_hub.errors import HfHubHTTPError
    import requests
except ImportError:
    print("请安装依赖: pip install huggingface_hub requests")
    sys.exit(1)

try:
    from gooey import Gooey, GooeyParser
except ImportError:
    print("请安装 gooey: pip install gooey")
    sys.exit(1)


def set_dpi_awareness():
    # 设置Windows高DPI支持
    if sys.platform == 'win32':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except:
                pass

set_dpi_awareness()
# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler('advanced_download.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)


class SettingsManager:
    """设置管理器 - 保存和加载用户的最后一次设置"""
    
    def __init__(self, settings_file: str = "last_settings.json"):
        self.settings_file = settings_file
        self.default_settings = {
            'url': '',
            'output_dir': './downloads',
            'token': '',
            'include_patterns': '',
            'exclude_patterns': '',
            'max_workers': 3,
            'progress_file': 'download_progress.json'
        }
        
    def load_settings(self) -> Dict[str, Any]:
        """加载上次保存的设置"""
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                logger.info(f"加载上次设置: {self.settings_file}")
                
                # 合并默认设置，确保所有字段都存在
                merged_settings = self.default_settings.copy()
                merged_settings.update(settings)
                return merged_settings
                
            except Exception as e:
                logger.warning(f"加载设置文件失败: {e}，使用默认设置")
        
        return self.default_settings.copy()
    
    def save_settings(self, settings: Dict[str, Any]):
        """保存当前设置"""
        try:
            # 先加载现有设置，然后更新
            existing_settings = self.load_settings()
            
            # 更新设置（只更新提供的字段）
            for key, value in settings.items():
                if key in self.default_settings:  # 只保存已知的设置字段
                    existing_settings[key] = value
            
            # 添加保存时间戳
            existing_settings['last_saved'] = datetime.now().isoformat()
            
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(existing_settings, f, ensure_ascii=False, indent=2)
            
            logger.info(f"设置已保存到: {self.settings_file}")
            
        except Exception as e:
            logger.error(f"保存设置失败: {e}")
    
    def get_display_info(self, settings: Dict[str, Any]) -> str:
        """获取设置的显示信息"""
        info_lines = []
        if settings.get('url'):
            info_lines.append(f"🔗 上次URL: {settings['url']}")
        if settings.get('token'):
            token_preview = settings['token'][:8] + "..." if len(settings['token']) > 8 else settings['token']
            info_lines.append(f"🔑 上次Token: {token_preview}")
        if settings.get('output_dir') != './downloads':
            info_lines.append(f"📁 上次目录: {settings['output_dir']}")
        if settings.get('include_patterns'):
            info_lines.append(f"📥 上次包含: {settings['include_patterns']}")
        if settings.get('exclude_patterns'):
            info_lines.append(f"🚫 上次排除: {settings['exclude_patterns']}")
        
        return "\n".join(info_lines) if info_lines else "📝 首次运行，使用默认设置"


class ProgressTracker:
    """进度跟踪器"""
    
    def __init__(self, progress_file: str):
        self.progress_file = progress_file
        self.data = {
            'repo_id': '',
            'total_files': 0,
            'completed_files': [],
            'failed_files': [],
            'current_file': '',
            'start_time': '',
            'last_update': '',
            'total_size_mb': 0,
            'downloaded_size_mb': 0,
            'file_details': {}  # 每个文件的详细信息
        }
        self.load_progress()
    
    def load_progress(self):
        """加载进度文件"""
        if os.path.exists(self.progress_file):
            try:
                with open(self.progress_file, 'r', encoding='utf-8') as f:
                    self.data = json.load(f)
                logger.info(f"加载进度文件: {len(self.data['completed_files'])} 个文件已完成")
            except Exception as e:
                logger.error(f"加载进度文件失败: {e}")
    
    def save_progress(self):
        """保存进度到文件"""
        self.data['last_update'] = datetime.now().isoformat()
        try:
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.error(f"保存进度文件失败: {e}")
    
    def init_task(self, repo_id: str, files: List[str]):
        """初始化任务"""
        current_files_set = set(files)
        
        # 检查是否需要重新初始化任务
        need_reset = False
        
        if self.data['repo_id'] != repo_id:
            # 不同仓库，重置进度
            need_reset = True
            reset_reason = "新仓库"
        else:
            # 同一仓库，检查文件列表是否有变化
            if 'all_files' not in self.data:
                # 旧版本进度文件，没有保存文件列表
                need_reset = True
                reset_reason = "升级进度文件格式"
            else:
                previous_files_set = set(self.data['all_files'])
                
                # 检查是否有新文件（之前被排除的文件）
                new_files = current_files_set - previous_files_set
                if new_files:
                    logger.info(f"发现 {len(new_files)} 个新文件（可能之前被排除）")
                    logger.info(f"新文件示例: {list(new_files)[:5]}")
                    
                    # 将新文件添加到任务中，但保留已完成的进度
                    self.data['all_files'] = files
                    self.data['total_files'] = len(files)
                    
                    # 清理已完成列表中不存在的文件
                    valid_completed = [f for f in self.data['completed_files'] if f in current_files_set]
                    removed_completed = len(self.data['completed_files']) - len(valid_completed)
                    if removed_completed > 0:
                        logger.info(f"清理了 {removed_completed} 个不再存在的已完成文件")
                    self.data['completed_files'] = valid_completed
                    
                    # 清理失败列表中不存在的文件
                    valid_failed = [f for f in self.data['failed_files'] if f in current_files_set]
                    self.data['failed_files'] = valid_failed
                    
                    print(f"📋 任务已更新:")
                    print(f"   📁 总文件数: {len(files)}")
                    print(f"   ✅ 已完成: {len(valid_completed)}")
                    print(f"   🆕 新增文件: {len(new_files)}")
                    print(f"   📥 待下载: {len(files) - len(valid_completed)}")
                    
                    self.save_progress()
                    return
                
                # 检查是否有文件被移除
                removed_files = previous_files_set - current_files_set
                if removed_files:
                    logger.info(f"检测到 {len(removed_files)} 个文件被排除")
                    
                    # 更新文件列表，但保留进度
                    self.data['all_files'] = files
                    self.data['total_files'] = len(files)
                    
                    # 清理已完成列表中被排除的文件
                    valid_completed = [f for f in self.data['completed_files'] if f in current_files_set]
                    self.data['completed_files'] = valid_completed
                    
                    # 清理失败列表中被排除的文件
                    valid_failed = [f for f in self.data['failed_files'] if f in current_files_set]
                    self.data['failed_files'] = valid_failed
                    
                    print(f"📋 任务已更新（排除文件）:")
                    print(f"   📁 总文件数: {len(files)}")
                    print(f"   ✅ 已完成: {len(valid_completed)}")
                    print(f"   🚫 排除文件: {len(removed_files)}")
                    print(f"   📥 待下载: {len(files) - len(valid_completed)}")
                    
                    self.save_progress()
                    return
        
        if need_reset:
            # 重置进度
            logger.info(f"重置任务进度: {reset_reason}")
            self.data = {
                'repo_id': repo_id,
                'all_files': files,  # 保存完整文件列表
                'total_files': len(files),
                'completed_files': [],
                'failed_files': [],
                'current_file': '',
                'start_time': datetime.now().isoformat(),
                'last_update': '',
                'total_size_mb': 0,
                'downloaded_size_mb': 0,
                'file_details': {}
            }
            print(f"🆕 开始新任务:")
            print(f"   🎯 仓库: {repo_id}")
            print(f"   📁 总文件数: {len(files)}")
        
        self.save_progress()
    
    def mark_file_completed(self, filename: str, size_mb: float = 0):
        """标记文件完成"""
        if filename not in self.data['completed_files']:
            self.data['completed_files'].append(filename)
            self.data['downloaded_size_mb'] += size_mb
            self.data['file_details'][filename] = {
                'status': 'completed',
                'size_mb': size_mb,
                'completed_time': datetime.now().isoformat()
            }
        self.save_progress()
    
    def mark_file_failed(self, filename: str, error: str):
        """标记文件失败"""
        if filename not in self.data['failed_files']:
            self.data['failed_files'].append(filename)
            self.data['file_details'][filename] = {
                'status': 'failed',
                'error': error,
                'failed_time': datetime.now().isoformat()
            }
        self.save_progress()
    
    def set_current_file(self, filename: str):
        """设置当前处理的文件"""
        self.data['current_file'] = filename
        self.save_progress()
    
    def get_remaining_files(self, all_files: List[str]) -> List[str]:
        """获取剩余未下载的文件"""
        completed = set(self.data['completed_files'])
        return [f for f in all_files if f not in completed]
    
    def get_progress_info(self) -> Dict[str, Any]:
        """获取进度信息"""
        completed = len(self.data['completed_files'])
        total = self.data['total_files']
        progress_percent = (completed / total * 100) if total > 0 else 0
        
        # 计算速度
        if self.data['start_time']:
            start_time = datetime.fromisoformat(self.data['start_time'])
            elapsed = (datetime.now() - start_time).total_seconds()
            speed = completed / elapsed if elapsed > 0 else 0
            eta = (total - completed) / speed if speed > 0 else 0
        else:
            elapsed = 0
            speed = 0
            eta = 0
        
        return {
            'completed': completed,
            'total': total,
            'progress_percent': progress_percent,
            'failed': len(self.data['failed_files']),
            'current_file': self.data['current_file'],
            'elapsed_seconds': elapsed,
            'speed_files_per_second': speed,
            'eta_seconds': eta,
            'downloaded_size_mb': self.data['downloaded_size_mb']
        }


class AdvancedDownloader:
    """高级下载器"""
    
    def __init__(self, repo_id: str, token: Optional[str] = None, 
                 progress_file: str = "download_progress.json",
                 endpoint: str = "https://huggingface.co"):
        self.repo_id = repo_id
        self.token = token
        self.endpoint = endpoint
        self.progress = ProgressTracker(progress_file)
        self.api = HfApi(token=token, endpoint=endpoint)
        self.stop_flag = threading.Event()
        
    def get_file_info(self, filename: str) -> Dict[str, Any]:
        """获取文件信息"""
        try:
            # 使用指定的端点
            url = f"{self.endpoint}/{self.repo_id}/resolve/main/{filename}"
            headers = {}
            if self.token:
                headers['Authorization'] = f'Bearer {self.token}'
            
            response = requests.head(url, headers=headers, timeout=10)
            size_bytes = int(response.headers.get('content-length', 0))
            size_mb = size_bytes / (1024 * 1024)
            
            return {
                'size_bytes': size_bytes,
                'size_mb': size_mb,
                'url': url
            }
        except Exception as e:
            logger.warning(f"无法获取文件 {filename} 的信息: {e}")
            return {'size_bytes': 0, 'size_mb': 0, 'url': ''}
    
    def download_single_file(self, filename: str, local_dir: str, 
                           max_retries: int = 3) -> bool:
        """下载单个文件，支持重试"""
        local_path = os.path.join(local_dir, filename)
        local_file_dir = os.path.dirname(local_path)
        os.makedirs(local_file_dir, exist_ok=True)
        
        # 检查文件是否已存在且完整
        if os.path.exists(local_path):
            file_info = self.get_file_info(filename)
            if file_info['size_bytes'] > 0:
                local_size = os.path.getsize(local_path)
                if local_size == file_info['size_bytes']:
                    logger.info(f"文件已存在且完整，跳过: {filename}")
                    self.progress.mark_file_completed(filename, file_info['size_mb'])
                    return True
        
        for attempt in range(max_retries):
            if self.stop_flag.is_set():
                return False
                
            try:
                logger.info(f"下载文件 (尝试 {attempt + 1}/{max_retries}): {filename}")
                
                # 使用 hf_hub_download 下载文件
                downloaded_path = hf_hub_download(
                    repo_id=self.repo_id,
                    filename=filename,
                    local_dir=local_dir,
                    token=self.token,
                    force_download=False,  # 支持断点续传
                    endpoint=self.endpoint
                )
                
                # 获取文件大小
                file_size = os.path.getsize(downloaded_path) / (1024 * 1024)  # MB
                
                self.progress.mark_file_completed(filename, file_size)
                logger.info(f"✅ 下载成功: {filename} ({file_size:.2f} MB)")
                return True
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"下载失败 (尝试 {attempt + 1}/{max_retries}): {filename} - {error_msg}")
                
                if attempt == max_retries - 1:
                    self.progress.mark_file_failed(filename, error_msg)
                    return False
                
                # 等待后重试
                time.sleep(2 ** attempt)  # 指数退避
        
        return False
    
    def download_repository(self, local_dir: str, 
                          file_patterns: Optional[List[str]] = None,
                          ignore_patterns: Optional[List[str]] = None,
                          max_workers: int = 3) -> bool:
        """下载整个仓库"""
        
        print(f"🔍 获取仓库文件列表: {self.repo_id}")
        
        try:
            # 获取所有文件列表
            all_files = self.api.list_repo_files(repo_id=self.repo_id)
            
            # 应用文件过滤
            if file_patterns:
                import fnmatch
                filtered_files = []
                for file in all_files:
                    for pattern in file_patterns:
                        if fnmatch.fnmatch(file, pattern):
                            filtered_files.append(file)
                            break
                all_files = filtered_files
            
            if ignore_patterns:
                import fnmatch
                filtered_files = []
                for file in all_files:
                    should_ignore = False
                    for pattern in ignore_patterns:
                        if fnmatch.fnmatch(file, pattern):
                            should_ignore = True
                            break
                    if not should_ignore:
                        filtered_files.append(file)
                all_files = filtered_files
            
            print(f"📊 总文件数: {len(all_files)}")
            
            # 初始化进度跟踪
            self.progress.init_task(self.repo_id, all_files)
            
            # 获取剩余未下载的文件
            remaining_files = self.progress.get_remaining_files(all_files)
            print(f"📋 剩余文件数: {len(remaining_files)}")
            
            if not remaining_files:
                print("✅ 所有文件已下载完成！")
                return True
            
            # 创建输出目录
            os.makedirs(local_dir, exist_ok=True)
            
            # 开始下载
            print(f"🚀 开始下载到: {local_dir}")
            start_time = time.time()
            
            # 使用线程池下载（控制并发数）
            import concurrent.futures
            
            with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                # 提交所有下载任务
                future_to_file = {}
                for filename in remaining_files:
                    if self.stop_flag.is_set():
                        break
                    future = executor.submit(self.download_single_file, filename, local_dir)
                    future_to_file[future] = filename
                
                # 处理完成的任务
                for future in concurrent.futures.as_completed(future_to_file):
                    if self.stop_flag.is_set():
                        break
                        
                    filename = future_to_file[future]
                    self.progress.set_current_file(filename)
                    
                    try:
                        success = future.result()
                        
                        # 显示进度
                        progress_info = self.progress.get_progress_info()
                        print(f"\r📥 进度: {progress_info['completed']}/{progress_info['total']} "
                              f"({progress_info['progress_percent']:.1f}%) "
                              f"当前: {filename[:50]}...", end='', flush=True)
                        
                        # 每10个文件显示详细统计
                        if progress_info['completed'] % 10 == 0:
                            print(f"\n📊 统计信息:")
                            print(f"   ✅ 已完成: {progress_info['completed']}")
                            print(f"   ❌ 失败: {progress_info['failed']}")
                            print(f"   ⏱️ 速度: {progress_info['speed_files_per_second']:.2f} 文件/秒")
                            print(f"   📦 已下载: {progress_info['downloaded_size_mb']:.1f} MB")
                            if progress_info['eta_seconds'] > 0:
                                eta_minutes = progress_info['eta_seconds'] / 60
                                print(f"   ⏰ 预计剩余: {eta_minutes:.1f} 分钟")
                        
                    except Exception as e:
                        logger.error(f"处理文件 {filename} 时出错: {e}")
            
            # 最终统计
            end_time = time.time()
            duration = end_time - start_time
            final_progress = self.progress.get_progress_info()
            
            print(f"\n\n🎉 下载完成！")
            print(f"📊 最终统计:")
            print(f"   ✅ 成功: {final_progress['completed']} 个文件")
            print(f"   ❌ 失败: {final_progress['failed']} 个文件")
            print(f"   ⏱️ 总用时: {duration:.1f} 秒")
            print(f"   📦 总大小: {final_progress['downloaded_size_mb']:.1f} MB")
            print(f"   📁 保存位置: {local_dir}")
            
            return final_progress['failed'] == 0
            
        except Exception as e:
            logger.error(f"下载过程出错: {e}")
            return False
    
    def stop_download(self):
        """停止下载"""
        self.stop_flag.set()
        print("\n⏹️ 正在停止下载...")

version = "1.0"
git_url = "https://github.com/void-gfly/hf_downloader"

def parse_repo_url(url: str):
    """
    解析仓库URL，返回 (repo_id, is_mirror, endpoint)
    支持：
    - https://huggingface.co/username/repo
    - https://hf-mirror.com/username/repo
    - https://huggingface.co/username/repo/tree/branch
    """
    url = url.rstrip('/')
    
    # 检查是否是镜像站链接
    if 'hf-mirror.com' in url:
        is_mirror = True
        endpoint = 'https://hf-mirror.com'
        # 从镜像站URL提取repo_id
        if '/tree/' in url:
            repo_id = url.split('/tree/')[0].replace('https://hf-mirror.com/', '')
        else:
            repo_id = url.replace('https://hf-mirror.com/', '')
    else:
        is_mirror = False
        endpoint = 'https://huggingface.co'
        # 从官方URL提取repo_id
        if '/tree/' in url:
            repo_id = url.split('/tree/')[0].replace('https://huggingface.co/', '')
        else:
            repo_id = url.replace('https://huggingface.co/', '')
    
    return repo_id, is_mirror, endpoint

@Gooey(
    program_name=f"Hugging Face批量下载器 v{version} {git_url}",
    program_description="支持详细进度显示和断点续传的下载工具",
    default_size=(1920,1440),
    header_height=160,
    encoding='utf-8',
    language='chinese',
    show_success_modal=True,
    show_failure_modal=True,
    progress_regex=r"进度: (\d+)/(\d+)",
    progress_expr="x[0] / x[1] * 100"
)
def main():
    # 加载上次保存的设置
    settings_manager = SettingsManager()
    last_settings = settings_manager.load_settings()
    
    # 显示上次设置信息
    settings_info = settings_manager.get_display_info(last_settings)
    if settings_info != "📝 首次运行，使用默认设置":
        print("💾 加载上次设置:")
        print(settings_info)
        print("-" * 50)
    
    parser = GooeyParser(description="高级 Hugging Face 下载器")
    
    # 基本设置
    basic_group = parser.add_argument_group("基本设置")
    basic_group.add_argument(
        'url',
        metavar='仓库链接',
        help='支持官方链接或镜像站链接:\n官方: https://huggingface.co/用户名/仓库名\n镜像: https://hf-mirror.com/用户名/仓库名（自动加载上次使用的URL）',
        widget='TextField',
        default=last_settings['url']
    )
    
    basic_group.add_argument(
        'output_dir',
        metavar='下载目录',
        help='文件保存目录（自动加载上次使用的目录）',
        widget='DirChooser',
        default=last_settings['output_dir']
    )
    
    basic_group.add_argument(
        '--token',
        metavar='访问令牌',
        help='Hugging Face 访问令牌（自动加载上次使用的token）',
        widget='PasswordField',
        default=last_settings['token']
    )
    
    # 过滤设置
    filter_group = parser.add_argument_group("文件过滤")
    filter_group.add_argument(
        '--include-patterns',
        metavar='包含模式',
        help='要下载的文件模式，用逗号分隔 (例如: *.json,*.md)（自动加载上次设置）',
        widget='TextField',
        default=last_settings['include_patterns']
    )
    
    filter_group.add_argument(
        '--exclude-patterns',
        metavar='排除模式',
        help='要排除的文件模式，用逗号分隔 (例如: *.safetensors,*.bin)，留空表示不排除任何文件（自动加载上次设置）',
        widget='TextField',
        default=last_settings['exclude_patterns']
    )
    
    # 高级设置
    advanced_group = parser.add_argument_group("高级设置")
    advanced_group.add_argument(
        '--max-workers',
        metavar='并发数',
        help='同时下载的文件数（自动加载上次设置）',
        type=int,
        default=last_settings['max_workers'],
        widget='IntegerField'
    )
    
    advanced_group.add_argument(
        '--progress-file',
        metavar='进度文件',
        help='进度保存文件路径（自动加载上次设置）',
        widget='TextField',
        default=last_settings['progress_file']
    )
    

    
    args = parser.parse_args()
    
    # 保存当前设置
    current_settings = {
        'url': args.url,
        'output_dir': args.output_dir,
        'token': args.token,
        'include_patterns': args.include_patterns,
        'exclude_patterns': args.exclude_patterns,
        'max_workers': args.max_workers,
        'progress_file': args.progress_file
    }
    settings_manager.save_settings(current_settings)
    
    # 解析URL，支持镜像站
    repo_id, is_mirror, endpoint = parse_repo_url(args.url)
    token = args.token.strip() if args.token.strip() else None
    
    # 处理文件模式
    include_patterns = None
    if args.include_patterns.strip():
        include_patterns = [p.strip() for p in args.include_patterns.split(',')]
    
    exclude_patterns = None
    if args.exclude_patterns.strip():
        exclude_patterns = [p.strip() for p in args.exclude_patterns.split(',')]
    
    print(f"🎯 目标仓库: {repo_id}")
    print(f"📁 保存目录: {args.output_dir}")
    print(f"🔧 并发数: {args.max_workers}")
    print(f"📄 进度文件: {args.progress_file}")
    
    # 显示下载源信息
    if is_mirror:
        print(f"🌐 使用镜像站: {endpoint}")
        
        # 测试镜像站连接
        try:
            response = requests.head(endpoint, timeout=5)
            if response.status_code == 200:
                print(f"✅ 镜像站连接正常")
            else:
                print(f"⚠️ 镜像站响应异常 (状态码: {response.status_code})")
        except Exception as e:
            print(f"⚠️ 镜像站连接测试失败: {e}")
            print(f"💡 将继续尝试使用镜像站，如遇问题请使用官方链接")
    else:
        print(f"🌐 使用官方站点: {endpoint}")
    
    # 显示文件过滤设置
    if include_patterns:
        print(f"📥 包含模式: {include_patterns}")
    else:
        print(f"📥 包含模式: 无（下载所有文件）")
    
    if exclude_patterns:
        print(f"🚫 排除模式: {exclude_patterns}")
    else:
        print(f"✅ 排除模式: 无（不排除任何文件）")
    
    # 创建下载器
    downloader = AdvancedDownloader(
        repo_id=repo_id,
        token=token,
        progress_file=args.progress_file,
        endpoint=endpoint
    )
    
    # 创建输出目录
    output_dir = os.path.join(args.output_dir, repo_id.replace('/', '_'))
    
    try:
        # 开始下载
        success = downloader.download_repository(
            local_dir=output_dir,
            file_patterns=include_patterns,
            ignore_patterns=exclude_patterns,
            max_workers=args.max_workers
        )
        
        if success:
            print(f"\n🎉 所有文件下载成功！")
        else:
            print(f"\n⚠️ 部分文件下载失败，请查看日志")
            
    except KeyboardInterrupt:
        downloader.stop_download()
        print(f"\n⏹️ 下载已停止，进度已保存")
        print(f"💡 下次运行时将从中断处继续")
    except Exception as e:
        print(f"\n❌ 下载出错: {e}")
        logger.error(f"下载出错: {e}")


if __name__ == '__main__':
    main() 