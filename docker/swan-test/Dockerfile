ARG base_image
FROM ${base_image}

LABEL maintainer "CSIRO <email.address@domain.com>"

RUN echo "--------------- Installing system packages ---------------" && \
    apt -y update && \
    apt -y install python3-dev \
                   python3-pip

RUN echo "--------------- Installing python packages ---------------" && \
    update-alternatives --install /usr/bin/python python /usr/bin/python3 1 && \
    pip install --no-cache-dir numpy pytest

RUN echo "--------------- Adding swan tests ---------------"
ADD tests /tmp/tests