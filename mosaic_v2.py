#!/usr/local/bin/python3
#  --*-- coding:utf8 --*--

import getopt
import sys
import os

import logging
from PIL import Image
from multiprocessing import Process, Queue, cpu_count

TILE_SIZE = 30  # 素材图片大小
TILE_MATCH_RES = 10  #配置指数  ，值越大匹配度越高，执行时间越长
ENLARGEMENT = 4  # 生成的图片是原始图片的多少倍

TILE_BLOCK_SIZE = int(TILE_SIZE / max(min(TILE_MATCH_RES, TILE_SIZE), 1))
WORKER_COUNT = max(cpu_count() - 1, 1)
EOQ_VALUE = None
WARN_INFO = """ *缺少有效参数*
    参数:
        -i [--image]     : 原图片地址
        -t [--tiles_dir] : 素材目录地址
        -o [--outfile]   : 输出文件地址 【可选】
"""


class TileProcessor:
    def __init__(self, tiles_directory):
        self.tiles_directory = tiles_directory

    def __process_tile(self, tile_path):
        try:
            img = Image.open(tile_path)
            # tiles must be square, so get the largest square that fits inside the image
            w = img.size[0]
            h = img.size[1]
            min_dimension = min(w, h)
            w_crop = (w - min_dimension) / 2
            h_crop = (h - min_dimension) / 2
            img = img.crop((w_crop, h_crop, w - w_crop, h - h_crop))
            large_tile_img = img.resize((TILE_SIZE, TILE_SIZE), Image.ANTIALIAS)
            small_tile_img = img.resize((int(TILE_SIZE / TILE_BLOCK_SIZE), int(TILE_SIZE / TILE_BLOCK_SIZE)),
                                        Image.ANTIALIAS)
            return (large_tile_img.convert('RGB'), small_tile_img.convert('RGB'))
        except Exception as e:
            logging.warning(e)
            return (None, None)

    def get_tiles(self):
        large_tiles = []
        small_tiles = []

        logging.info('从 \'%s\' 获取图片素材...' % self.tiles_directory)

        # search the tiles directory recursively
        for root, subFolders, files in os.walk(self.tiles_directory):
            for tile_name in files:
                tile_path = os.path.join(root, tile_name)
                large_tile, small_tile = self.__process_tile(tile_path)
                logging.debug(large_tile)
                logging.debug(small_tile)
                if large_tile:
                    large_tiles.append(large_tile)
                    small_tiles.append(small_tile)

        logging.info('读取素材 %s 完成.' % len(large_tiles))

        return (large_tiles, small_tiles)


class TargetImage:
    def __init__(self, image_path):
        self.image_path = image_path

    def get_data(self):
        logging.info('处理主图片...')
        img = Image.open(self.image_path)
        w = img.size[0] * ENLARGEMENT
        h = img.size[1] * ENLARGEMENT
        large_img = img.resize((w, h), Image.ANTIALIAS)
        w_diff = (w % TILE_SIZE) / 2
        h_diff = (h % TILE_SIZE) / 2

        # if necesary, crop the image slightly so we use a whole number of tiles horizontally and vertically
        if w_diff or h_diff:
            large_img = large_img.crop((w_diff, h_diff, w - w_diff, h - h_diff))

        small_img = large_img.resize((int(w / TILE_BLOCK_SIZE), int(h / TILE_BLOCK_SIZE)), Image.ANTIALIAS)

        image_data = (large_img.convert('RGB'), small_img.convert('RGB'))

        logging.info('主图片处理完成.')

        return image_data


class TileFitter:
    def __init__(self, tiles_data):
        self.tiles_data = tiles_data

    def __get_tile_diff(self, t1, t2, bail_out_value):
        diff = 0
        for i in range(len(t1)):
            # diff += (abs(t1[i][0] - t2[i][0]) + abs(t1[i][1] - t2[i][1]) + abs(t1[i][2] - t2[i][2]))
            diff += ((t1[i][0] - t2[i][0]) ** 2 + (t1[i][1] - t2[i][1]) ** 2 + (t1[i][2] - t2[i][2]) ** 2)
            if diff > bail_out_value:
                # we know already that this isnt going to be the best fit, so no point continuing with this tile
                return diff
        return diff

    def get_best_fit_tile(self, img_data):
        best_fit_tile_index = None
        min_diff = sys.maxsize
        tile_index = 0

        # go through each tile in turn looking for the best match for the part of the image represented by 'img_data'
        for tile_data in self.tiles_data:
            diff = self.__get_tile_diff(img_data, tile_data, min_diff)
            # logging.info(diff)
            if diff < min_diff:
                min_diff = diff
                best_fit_tile_index = tile_index
            tile_index += 1

        return best_fit_tile_index


def fit_tiles(work_queue, result_queue, tiles_data):
    # this function gets run by the worker processes, one on each CPU core
    tile_fitter = TileFitter(tiles_data)

    while True:
        try:
            img_data, img_coords = work_queue.get(True)
            if img_data == EOQ_VALUE:
                break
            tile_index = tile_fitter.get_best_fit_tile(img_data)
            result_queue.put((img_coords, tile_index))
        except KeyboardInterrupt:
            pass

    # let the result handler know that this worker has finished everything
    result_queue.put((EOQ_VALUE, EOQ_VALUE))


class ProgressCounter:
    def __init__(self, total):
        self.total = total
        self.counter = 0

    def update(self):
        self.counter += 1
        sys.stdout.write(
            "进度: %s%% %s" % ((100 * self.counter / self.total), "\r"))

        # sys.stdout.write("Progress: %s%% %s" % (100 * self.counter / self.total, "\r"))

    sys.stdout.flush()


class MosaicImage:
    def __init__(self, original_img, outfile):
        self.image = Image.new(original_img.mode, original_img.size)
        self.x_tile_count = int(original_img.size[0] / TILE_SIZE)
        self.y_tile_count = int(original_img.size[1] / TILE_SIZE)
        self.total_tiles = self.x_tile_count * self.y_tile_count
        self.outfile = outfile

    def add_tile(self, tile_data, coords):
        img = Image.new('RGB', (TILE_SIZE, TILE_SIZE))
        img.putdata(tile_data)
        self.image.paste(img, coords)

    def save(self, path):
        self.image.save(path)


def build_mosaic(result_queue, all_tile_data_large, original_img_large, outfile):
    mosaic = MosaicImage(original_img_large, outfile)

    active_workers = WORKER_COUNT
    while True:
        try:
            img_coords, best_fit_tile_index = result_queue.get()

            if img_coords == EOQ_VALUE:
                active_workers -= 1
                if not active_workers:
                    break
            else:
                tile_data = all_tile_data_large[best_fit_tile_index]
                mosaic.add_tile(tile_data, img_coords)

        except KeyboardInterrupt:
            pass

    mosaic.save(mosaic.outfile)
    logging.info('============ 生成成功 ============')


def compose(original_img, tiles, outfile):
    logging.info('生成图片中,按下 Ctrl-C 中断...')
    original_img_large, original_img_small = original_img
    tiles_large, tiles_small = tiles

    mosaic = MosaicImage(original_img_large, outfile)

    all_tile_data_large = list(map(lambda tile: list(tile.getdata()), tiles_large))
    all_tile_data_small = list(map(lambda tile: list(tile.getdata()), tiles_small))

    work_queue = Queue(WORKER_COUNT)
    result_queue = Queue()

    try:
        # start the worker processes that will build the mosaic image
        Process(target=build_mosaic, args=(result_queue, all_tile_data_large, original_img_large, outfile)).start()

        # start the worker processes that will perform the tile fitting
        for n in range(WORKER_COUNT):
            Process(target=fit_tiles, args=(work_queue, result_queue, all_tile_data_small)).start()

        progress = ProgressCounter(mosaic.x_tile_count * mosaic.y_tile_count)
        for x in range(mosaic.x_tile_count):
            for y in range(mosaic.y_tile_count):
                large_box = (x * TILE_SIZE, y * TILE_SIZE, (x + 1) * TILE_SIZE, (y + 1) * TILE_SIZE)
                small_box = (
                    x * TILE_SIZE / TILE_BLOCK_SIZE, y * TILE_SIZE / TILE_BLOCK_SIZE,
                    (x + 1) * TILE_SIZE / TILE_BLOCK_SIZE,
                    (y + 1) * TILE_SIZE / TILE_BLOCK_SIZE)
                work_queue.put((list(original_img_small.crop(small_box).getdata()), large_box))
                progress.update()

    except KeyboardInterrupt:
        logging.info('\nHalting, saving partial image please wait...')

    finally:
        # put these special values onto the queue to let the workers know they can terminate
        for n in range(WORKER_COUNT):
            work_queue.put((EOQ_VALUE, EOQ_VALUE))


def mosaic(img_path, tiles_path, outfile):
    tiles_data = TileProcessor(tiles_path).get_tiles()
    image_data = TargetImage(img_path).get_data()
    compose(image_data, tiles_data, output)




if __name__ == '__main__':
    logging.basicConfig(filename='mosaic.log',
                        format='%(asctime)s  %(filename)s : %(levelname)s  %(message)s',
                        level=logging.INFO)
    logging.getLogger().addHandler(logging.StreamHandler())

    opts, args = getopt.gnu_getopt(sys.argv[1:], 'i:t:o:ts:tr:e:', ['image=', 'tiles_dir=', 'outfile=',""])

    base_image = None
    tiles_dir = None
    output = None
    for k, v in opts:
        if k in ("-i", "--image"):
            base_image = v
        if k in ("-t", "--tiles_dir"):
            tiles_dir = v
        if k in ("-o", "--outfile"):
            output = v

    # base_image = None
    # tiles_dir = None

    for value in (base_image, tiles_dir):
        if value is None:
            logging.error(WARN_INFO)
            sys.exit()

    if output is None:
        output = './mosaic.jpg'

    mosaic(base_image, tiles_dir, output)
