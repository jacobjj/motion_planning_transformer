# A script to run ompl-docker

docker run -it \
    -p $1:8800 \
    --gpus all \
    --shm-size="4g"\
    -e DISPLAY=$DISPLAY \
    -e QT_X11_NO_MITSHM=1 \
    -v $XAUTH:/root/.Xauthority \
    -v /tmp/.X11-unix:/tmp/.X11-unix:rw \
    -v ~/global_planner:/workspace \
    -v ~/global_planner_data:/root/data \
    pytorch/pytorch:1.7.1-cuda11.0-cudnn8-jupyter-ompl\
    bash
