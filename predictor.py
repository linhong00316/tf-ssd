import tensorflow as tf
from utils import bbox_utils, data_utils, drawing_utils, io_utils, train_utils

args = io_utils.handle_args()
if args.handle_gpu:
    io_utils.handle_gpu_compatibility()

batch_size = 1
use_custom_images = False
custom_image_path = "data/images/"
backbone = args.backbone
io_utils.is_valid_backbone(backbone)
#
if backbone == "mobilenet_v2":
    from models.ssd_mobilenet_v2 import get_model, init_model
else:
    from models.ssd_vgg16 import get_model, init_model
#
hyper_params = train_utils.get_hyper_params(backbone)
#
test_data, info = data_utils.get_dataset("voc/2007", "test")
labels = data_utils.get_labels(info)
# We add 1 class for background
hyper_params["total_labels"] = len(labels) + 1
img_size = hyper_params["img_size"]

if use_custom_images:
    test_data = data_utils.get_image_data_from_folder(custom_image_path, img_size, img_size)
else:
    test_data = test_data.map(lambda x : data_utils.preprocessing(x, img_size, img_size))
    padded_shapes, padding_values = data_utils.get_padded_batch_params()
    test_data = test_data.padded_batch(batch_size, padded_shapes=padded_shapes, padding_values=padding_values)

ssd_model = get_model(hyper_params)
ssd_model_path = io_utils.get_model_path(backbone)
ssd_model.load_weights(ssd_model_path)

prior_boxes = bbox_utils.generate_prior_boxes(hyper_params["feature_map_shapes"], hyper_params["aspect_ratios"])

background_label = "bg"
labels = [background_label] + labels
bg_id = labels.index(background_label)

for image_data in test_data:
    img, _, _ = image_data
    pred_bbox_deltas, pred_labels = ssd_model.predict_on_batch(img)
    #
    pred_bbox_deltas *= hyper_params["variances"]
    pred_bboxes = bbox_utils.get_bboxes_from_deltas(prior_boxes, pred_bbox_deltas)
    pred_bboxes = tf.clip_by_value(pred_bboxes, 0, 1)
    #
    pred_labels = tf.cast(pred_labels, tf.float32)
    reshaped_pred_bboxes = tf.reshape(pred_bboxes, (batch_size, pred_bbox_deltas.shape[1], 1, 4))
    # Remove background predictions
    pred_labels_map = tf.argmax(pred_labels, 2, output_type=tf.int32)
    valid_cond = tf.not_equal(pred_labels_map, bg_id)
    #
    valid_bboxes = tf.expand_dims(reshaped_pred_bboxes[valid_cond], 0)
    valid_labels = tf.expand_dims(pred_labels[valid_cond], 0)
    #
    nms_bboxes, nmsed_scores, nmsed_classes, valid_detections = bbox_utils.non_max_suppression(valid_bboxes, valid_labels,
                                                                                               max_output_size_per_class=10,
                                                                                               max_total_size=200, score_threshold=0.5)
    denormalized_bboxes = bbox_utils.denormalize_bboxes(nms_bboxes[0], img_size, img_size)
    drawing_utils.draw_bboxes_with_labels(img[0], denormalized_bboxes, nmsed_classes[0], nmsed_scores[0], labels)
